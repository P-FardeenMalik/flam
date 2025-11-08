"""CLI interface for QueueCTL"""

import click
import json
import sys
from colorama import init, Fore, Style
from datetime import datetime

from .config import Config
from .storage import JobStorage
from .queue import JobQueue
from .worker import WorkerManager

# Initialize colorama for Windows
init()


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display"""
    if not ts:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return ts


def print_success(message: str):
    """Print success message"""
    print(f"{Fore.GREEN}[OK]{Style.RESET_ALL} {message}")


def print_error(message: str):
    """Print error message"""
    print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")


def print_info(message: str):
    """Print info message"""
    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {message}")


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """QueueCTL - A CLI-based background job queue system
    
    Manage background jobs with worker processes, automatic retries,
    and a Dead Letter Queue for failed jobs.
    """
    pass


@cli.command()
@click.argument('job_json')
def enqueue(job_json):
    """Enqueue a new job
    
    JOB_JSON should be a JSON string containing at least 'id' and 'command' fields.
    
    Example:
        queuectl enqueue '{"id":"job1","command":"echo Hello"}'
    """
    try:
        job_data = json.loads(job_json)
        
        if 'id' not in job_data or 'command' not in job_data:
            print_error("Job must contain 'id' and 'command' fields")
            sys.exit(1)
        
        config = Config()
        storage = JobStorage(config.get_db_path())
        queue = JobQueue(storage, config)
        
        job = queue.enqueue_from_dict(job_data)
        
        print_success(f"Job '{job['id']}' enqueued successfully")
        print(f"  Command: {job['command']}")
        print(f"  State: {job['state']}")
        print(f"  Max Retries: {job['max_retries']}")
        
    except json.JSONDecodeError:
        print_error("Invalid JSON format")
        sys.exit(1)
    except Exception as e:
        print_error(f"Failed to enqueue job: {e}")
        sys.exit(1)


@cli.group()
def worker():
    """Manage worker processes"""
    pass


@worker.command()
@click.option('--count', '-c', default=1, help='Number of workers to start')
def start(count):
    """Start one or more worker processes
    
    Example:
        queuectl worker start --count 3
    """
    try:
        config = Config()
        manager = WorkerManager(config)
        
        workers = manager.start_workers(count)
        
        print_success(f"Started {len(workers)} worker(s)")
        for w in workers:
            print(f"  Worker {w['id']} (PID: {w['pid']})")
        
    except Exception as e:
        print_error(f"Failed to start workers: {e}")
        sys.exit(1)


@worker.command()
def stop():
    """Stop all running workers gracefully
    
    Example:
        queuectl worker stop
    """
    try:
        config = Config()
        manager = WorkerManager(config)
        
        count = manager.stop_workers()
        
        if count > 0:
            print_success(f"Stopped {count} worker(s)")
        else:
            print_info("No workers were running")
        
    except Exception as e:
        print_error(f"Failed to stop workers: {e}")
        sys.exit(1)


@worker.command()
def list():
    """List all running workers
    
    Example:
        queuectl worker list
    """
    try:
        config = Config()
        manager = WorkerManager(config)
        
        workers = manager.get_running_workers()
        
        if workers:
            print(f"\n{Fore.CYAN}Running Workers:{Style.RESET_ALL}")
            print(f"{'ID':<30} {'PID':<10} {'Started At':<20}")
            print("-" * 60)
            for w in workers:
                print(f"{w['id']:<30} {w['pid']:<10} {format_timestamp(w.get('started_at')):<20}")
        else:
            print_info("No workers are currently running")
        
    except Exception as e:
        print_error(f"Failed to list workers: {e}")
        sys.exit(1)


@cli.command()
def status():
    """Show summary of all job states and active workers
    
    Example:
        queuectl status
    """
    try:
        config = Config()
        storage = JobStorage(config.get_db_path())
        queue = JobQueue(storage, config)
        manager = WorkerManager(config)
        
        status_data = queue.get_status()
        workers = manager.get_running_workers()
        
        print(f"\n{Fore.CYAN}Queue Status:{Style.RESET_ALL}")
        print(f"  Total Jobs: {status_data['total_jobs']}")
        print(f"  {Fore.YELLOW}Pending:{Style.RESET_ALL} {status_data['pending']}")
        print(f"  {Fore.BLUE}Processing:{Style.RESET_ALL} {status_data['processing']}")
        print(f"  {Fore.GREEN}Completed:{Style.RESET_ALL} {status_data['completed']}")
        print(f"  {Fore.MAGENTA}Failed:{Style.RESET_ALL} {status_data['failed']}")
        print(f"  {Fore.RED}Dead (DLQ):{Style.RESET_ALL} {status_data['dead']}")
        
        print(f"\n{Fore.CYAN}Workers:{Style.RESET_ALL}")
        print(f"  Active Workers: {len(workers)}")
        
    except Exception as e:
        print_error(f"Failed to get status: {e}")
        sys.exit(1)


@cli.command()
@click.option('--state', '-s', help='Filter by state (pending, processing, completed, failed, dead)')
@click.option('--limit', '-l', default=20, help='Maximum number of jobs to show')
def list(state, limit):
    """List jobs, optionally filtered by state
    
    Example:
        queuectl list --state pending
        queuectl list --limit 50
    """
    try:
        config = Config()
        storage = JobStorage(config.get_db_path())
        queue = JobQueue(storage, config)
        
        jobs = queue.list_jobs(state=state, limit=limit)
        
        if jobs:
            title = f"Jobs" + (f" ({state})" if state else "")
            print(f"\n{Fore.CYAN}{title}:{Style.RESET_ALL}")
            print(f"{'ID':<20} {'State':<12} {'Command':<30} {'Attempts':<10} {'Created At':<20}")
            print("-" * 92)
            
            for job in jobs:
                state_color = {
                    'pending': Fore.YELLOW,
                    'processing': Fore.BLUE,
                    'completed': Fore.GREEN,
                    'failed': Fore.MAGENTA,
                    'dead': Fore.RED
                }.get(job['state'], '')
                
                command = job['command'][:27] + '...' if len(job['command']) > 30 else job['command']
                
                print(f"{job['id']:<20} "
                      f"{state_color}{job['state']:<12}{Style.RESET_ALL} "
                      f"{command:<30} "
                      f"{job['attempts']}/{job['max_retries']:<10} "
                      f"{format_timestamp(job['created_at']):<20}")
        else:
            print_info(f"No jobs found" + (f" with state '{state}'" if state else ""))
        
    except Exception as e:
        print_error(f"Failed to list jobs: {e}")
        sys.exit(1)


@cli.group()
def dlq():
    """Manage Dead Letter Queue (permanently failed jobs)"""
    pass


@dlq.command()
@click.option('--limit', '-l', default=20, help='Maximum number of jobs to show')
def list(limit):
    """List jobs in the Dead Letter Queue
    
    Example:
        queuectl dlq list
    """
    try:
        config = Config()
        storage = JobStorage(config.get_db_path())
        queue = JobQueue(storage, config)
        
        jobs = queue.list_jobs(state='dead', limit=limit)
        
        if jobs:
            print(f"\n{Fore.RED}Dead Letter Queue:{Style.RESET_ALL}")
            print(f"{'ID':<20} {'Command':<30} {'Attempts':<10} {'Error':<30}")
            print("-" * 90)
            
            for job in jobs:
                command = job['command'][:27] + '...' if len(job['command']) > 30 else job['command']
                error = (job['error'] or '')[:27] + '...' if job.get('error') and len(job['error']) > 30 else (job.get('error') or 'N/A')
                
                print(f"{job['id']:<20} {command:<30} {job['attempts']:<10} {error:<30}")
        else:
            print_info("Dead Letter Queue is empty")
        
    except Exception as e:
        print_error(f"Failed to list DLQ jobs: {e}")
        sys.exit(1)


@dlq.command()
@click.argument('job_id')
def retry(job_id):
    """Retry a job from the Dead Letter Queue
    
    JOB_ID is the ID of the job to retry.
    
    Example:
        queuectl dlq retry job1
    """
    try:
        config = Config()
        storage = JobStorage(config.get_db_path())
        queue = JobQueue(storage, config)
        
        if queue.retry_dlq_job(job_id):
            print_success(f"Job '{job_id}' moved back to pending queue")
        else:
            print_error(f"Job '{job_id}' not found in DLQ or already retried")
            sys.exit(1)
        
    except Exception as e:
        print_error(f"Failed to retry job: {e}")
        sys.exit(1)


@cli.group()
def config():
    """Manage configuration settings"""
    pass


@config.command()
def show():
    """Show current configuration
    
    Example:
        queuectl config show
    """
    try:
        cfg = Config()
        config_data = cfg.get_all()
        
        print(f"\n{Fore.CYAN}Configuration:{Style.RESET_ALL}")
        for key, value in config_data.items():
            print(f"  {key}: {value}")
        
    except Exception as e:
        print_error(f"Failed to show config: {e}")
        sys.exit(1)


@config.command()
@click.argument('key')
@click.argument('value')
def set(key, value):
    """Set a configuration value
    
    KEY is the configuration key (e.g., max-retries, backoff-base)
    VALUE is the new value
    
    Example:
        queuectl config set max-retries 5
        queuectl config set backoff-base 3
    """
    try:
        # Convert key from kebab-case to snake_case
        key = key.replace('-', '_')
        
        # Try to convert value to appropriate type
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass  # Keep as string
        
        cfg = Config()
        cfg.set(key, value)
        
        print_success(f"Configuration updated: {key} = {value}")
        
    except Exception as e:
        print_error(f"Failed to set config: {e}")
        sys.exit(1)


@cli.command()
@click.argument('job_id')
def info(job_id):
    """Show detailed information about a job
    
    JOB_ID is the ID of the job to inspect.
    
    Example:
        queuectl info job1
    """
    try:
        config = Config()
        storage = JobStorage(config.get_db_path())
        queue = JobQueue(storage, config)
        
        job = queue.get_job(job_id)
        
        if job:
            state_color = {
                'pending': Fore.YELLOW,
                'processing': Fore.BLUE,
                'completed': Fore.GREEN,
                'failed': Fore.MAGENTA,
                'dead': Fore.RED
            }.get(job['state'], '')
            
            print(f"\n{Fore.CYAN}Job Information:{Style.RESET_ALL}")
            print(f"  ID: {job['id']}")
            print(f"  Command: {job['command']}")
            print(f"  State: {state_color}{job['state']}{Style.RESET_ALL}")
            print(f"  Attempts: {job['attempts']}/{job['max_retries']}")
            print(f"  Created At: {format_timestamp(job['created_at'])}")
            print(f"  Updated At: {format_timestamp(job['updated_at'])}")
            
            if job.get('locked_by'):
                print(f"  Locked By: {job['locked_by']}")
                print(f"  Locked At: {format_timestamp(job['locked_at'])}")
            
            if job.get('next_retry_at'):
                print(f"  Next Retry: {format_timestamp(job['next_retry_at'])}")
            
            if job.get('error'):
                print(f"  {Fore.RED}Error:{Style.RESET_ALL} {job['error']}")
            
            if job.get('output'):
                print(f"  {Fore.GREEN}Output:{Style.RESET_ALL} {job['output']}")
        else:
            print_error(f"Job '{job_id}' not found")
            sys.exit(1)
        
    except Exception as e:
        print_error(f"Failed to get job info: {e}")
        sys.exit(1)


if __name__ == '__main__':
    cli()
