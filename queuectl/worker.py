"""Worker process for executing jobs"""

import os
import sys
import time
import signal
import subprocess
import json
from typing import Optional
from datetime import datetime

from .storage import JobStorage
from .queue import JobQueue
from .config import Config


class Worker:
    """Worker process that executes jobs from the queue"""
    
    def __init__(self, worker_id: str, config: Config):
        """Initialize worker
        
        Args:
            worker_id: Unique worker identifier
            config: Config instance
        """
        self.worker_id = worker_id
        self.config = config
        self.storage = JobStorage(config.get_db_path())
        self.queue = JobQueue(self.storage, config)
        self.running = True
        self.current_job_id = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[Worker {self.worker_id}] Received shutdown signal. Finishing current job...")
        self.running = False
    
    def _execute_command(self, command: str) -> tuple[int, str, str]:
        """Execute a shell command
        
        Args:
            command: Shell command to execute
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        try:
            # Use shell=True to support complex commands
            # On Windows, use cmd.exe
            if sys.platform == 'win32':
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
            else:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    executable='/bin/bash'
                )
            
            stdout, stderr = process.communicate()
            return process.returncode, stdout, stderr
            
        except Exception as e:
            return 1, '', str(e)
    
    def _process_job(self, job: dict) -> bool:
        """Process a single job
        
        Args:
            job: Job dictionary
            
        Returns:
            True if job was processed successfully
        """
        job_id = job['id']
        command = job['command']
        
        print(f"[Worker {self.worker_id}] Processing job {job_id}: {command}")
        
        # Execute the command
        exit_code, stdout, stderr = self._execute_command(command)
        
        # Determine if job succeeded
        if exit_code == 0:
            # Success
            output = stdout.strip() if stdout else None
            self.queue.mark_completed(job_id, output=output)
            print(f"[Worker {self.worker_id}] Job {job_id} completed successfully")
            return True
        else:
            # Failure
            error = stderr.strip() if stderr else f"Command exited with code {exit_code}"
            self.queue.mark_failed(job_id, error=error)
            
            # Check if job moved to DLQ
            updated_job = self.queue.get_job(job_id)
            if updated_job and updated_job['state'] == 'dead':
                print(f"[Worker {self.worker_id}] Job {job_id} moved to DLQ after {updated_job['attempts']} attempts")
            else:
                print(f"[Worker {self.worker_id}] Job {job_id} failed (attempt {updated_job['attempts']}/{updated_job['max_retries']}). Will retry.")
            
            return False
    
    def run(self):
        """Main worker loop"""
        print(f"[Worker {self.worker_id}] Started")
        poll_interval = self.config.get('worker_poll_interval', 1)
        
        try:
            while self.running:
                # Get next job
                job = self.queue.get_next_job()
                
                if job:
                    # Try to acquire lock on the job
                    if self.queue.acquire_job(job['id'], self.worker_id):
                        self.current_job_id = job['id']
                        try:
                            self._process_job(job)
                        finally:
                            # Always release the lock
                            self.queue.release_job(job['id'])
                            self.current_job_id = None
                    # If lock acquisition failed, another worker got it
                else:
                    # No jobs available, sleep
                    time.sleep(poll_interval)
            
            print(f"[Worker {self.worker_id}] Shutdown complete")
            
        except Exception as e:
            print(f"[Worker {self.worker_id}] Error: {e}")
            # Release lock if we have one
            if self.current_job_id:
                self.queue.release_job(self.current_job_id)
            raise


class WorkerManager:
    """Manages worker processes"""
    
    def __init__(self, config: Config):
        """Initialize worker manager
        
        Args:
            config: Config instance
        """
        self.config = config
        self.pid_file = config.get_worker_pid_file()
    
    def _read_pid_file(self) -> dict:
        """Read worker PID file"""
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _write_pid_file(self, data: dict):
        """Write worker PID file"""
        os.makedirs(os.path.dirname(self.pid_file), exist_ok=True)
        with open(self.pid_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is running"""
        try:
            if sys.platform == 'win32':
                # On Windows, use tasklist
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True,
                    text=True
                )
                return str(pid) in result.stdout
            else:
                # On Unix, send signal 0
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, PermissionError, OSError):
            return False
    
    def get_running_workers(self) -> list:
        """Get list of running workers
        
        Returns:
            List of worker info dictionaries
        """
        workers_data = self._read_pid_file()
        running_workers = []
        
        for worker_id, info in workers_data.get('workers', {}).items():
            pid = info.get('pid')
            if pid and self._is_process_running(pid):
                running_workers.append({
                    'id': worker_id,
                    'pid': pid,
                    'started_at': info.get('started_at')
                })
        
        return running_workers
    
    def start_workers(self, count: int = 1) -> list:
        """Start worker processes
        
        Args:
            count: Number of workers to start
            
        Returns:
            List of started worker info
        """
        started_workers = []
        workers_data = self._read_pid_file()
        
        if 'workers' not in workers_data:
            workers_data['workers'] = {}
        
        for i in range(count):
            worker_id = f"worker-{int(time.time() * 1000)}-{i}"
            
            # Start worker process
            if sys.platform == 'win32':
                # On Windows, use pythonw to run in background
                process = subprocess.Popen(
                    [sys.executable, '-m', 'queuectl.worker', worker_id],
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            else:
                # On Unix, use nohup
                process = subprocess.Popen(
                    [sys.executable, '-m', 'queuectl.worker', worker_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    preexec_fn=os.setpgrp
                )
            
            worker_info = {
                'id': worker_id,
                'pid': process.pid,
                'started_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            workers_data['workers'][worker_id] = worker_info
            started_workers.append(worker_info)
            
            # Small delay between starting workers
            time.sleep(0.1)
        
        self._write_pid_file(workers_data)
        return started_workers
    
    def stop_workers(self) -> int:
        """Stop all running workers
        
        Returns:
            Number of workers stopped
        """
        workers = self.get_running_workers()
        stopped_count = 0
        
        for worker in workers:
            try:
                pid = worker['pid']
                if sys.platform == 'win32':
                    # On Windows, use taskkill
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                                   capture_output=True)
                else:
                    # On Unix, send SIGTERM
                    os.kill(pid, signal.SIGTERM)
                stopped_count += 1
            except Exception:
                pass
        
        # Clear the PID file
        self._write_pid_file({'workers': {}})
        
        return stopped_count


def main():
    """Entry point for worker process"""
    if len(sys.argv) < 2:
        print("Usage: python -m queuectl.worker <worker_id>")
        sys.exit(1)
    
    worker_id = sys.argv[1]
    config = Config()
    
    worker = Worker(worker_id, config)
    worker.run()


if __name__ == '__main__':
    main()
