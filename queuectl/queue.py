"""Job queue manager for handling job lifecycle and retries"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from .storage import JobStorage
from .config import Config


class JobQueue:
    """Manages job queue operations"""
    
    def __init__(self, storage: JobStorage, config: Config):
        """Initialize job queue
        
        Args:
            storage: JobStorage instance
            config: Config instance
        """
        self.storage = storage
        self.config = config
    
    def enqueue(self, command: str, job_id: Optional[str] = None, 
                max_retries: Optional[int] = None) -> Dict[str, Any]:
        """Add a new job to the queue
        
        Args:
            command: Shell command to execute
            job_id: Optional job ID (generated if not provided)
            max_retries: Optional max retry count (uses config default if not provided)
            
        Returns:
            Created job dictionary
        """
        if job_id is None:
            job_id = str(uuid.uuid4())
        
        if max_retries is None:
            max_retries = self.config.get('max_retries', 3)
        
        job = {
            'id': job_id,
            'command': command,
            'state': 'pending',
            'attempts': 0,
            'max_retries': max_retries,
        }
        
        return self.storage.create_job(job)
    
    def enqueue_from_dict(self, job_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Enqueue a job from a dictionary
        
        Args:
            job_dict: Job dictionary with at least id and command
            
        Returns:
            Created job dictionary
        """
        # Set defaults if not provided
        if 'max_retries' not in job_dict:
            job_dict['max_retries'] = self.config.get('max_retries', 3)
        if 'state' not in job_dict:
            job_dict['state'] = 'pending'
        if 'attempts' not in job_dict:
            job_dict['attempts'] = 0
        
        return self.storage.create_job(job_dict)
    
    def mark_completed(self, job_id: str, output: str = None) -> bool:
        """Mark a job as completed
        
        Args:
            job_id: Job ID
            output: Optional job output
            
        Returns:
            True if job was updated
        """
        updates = {
            'state': 'completed',
            'output': output,
        }
        return self.storage.update_job(job_id, updates)
    
    def mark_failed(self, job_id: str, error: str = None) -> bool:
        """Mark a job as failed and schedule retry or move to DLQ
        
        Args:
            job_id: Job ID
            error: Optional error message
            
        Returns:
            True if job was updated
        """
        job = self.storage.get_job(job_id)
        if not job:
            return False
        
        attempts = job['attempts'] + 1
        max_retries = job['max_retries']
        
        # Check if we should move to DLQ
        if attempts >= max_retries:
            updates = {
                'state': 'dead',
                'attempts': attempts,
                'error': error,
            }
        else:
            # Schedule retry with exponential backoff
            backoff_base = self.config.get('backoff_base', 2)
            delay_seconds = backoff_base ** attempts
            next_retry = datetime.utcnow() + timedelta(seconds=delay_seconds)
            
            updates = {
                'state': 'failed',
                'attempts': attempts,
                'error': error,
                'next_retry_at': next_retry.isoformat() + 'Z',
            }
        
        return self.storage.update_job(job_id, updates)
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID
        
        Args:
            job_id: Job ID
            
        Returns:
            Job dictionary or None
        """
        return self.storage.get_job(job_id)
    
    def list_jobs(self, state: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List jobs, optionally filtered by state
        
        Args:
            state: Filter by state
            limit: Maximum number of jobs
            
        Returns:
            List of job dictionaries
        """
        return self.storage.list_jobs(state=state, limit=limit)
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue status summary
        
        Returns:
            Status dictionary with job counts by state
        """
        counts = self.storage.get_job_counts()
        total = sum(counts.values())
        
        return {
            'total_jobs': total,
            'pending': counts.get('pending', 0),
            'processing': counts.get('processing', 0),
            'completed': counts.get('completed', 0),
            'failed': counts.get('failed', 0),
            'dead': counts.get('dead', 0),
        }
    
    def retry_dlq_job(self, job_id: str) -> bool:
        """Retry a job from the Dead Letter Queue
        
        Args:
            job_id: Job ID
            
        Returns:
            True if job was moved back to pending
        """
        job = self.storage.get_job(job_id)
        if not job or job['state'] != 'dead':
            return False
        
        # Reset job state for retry
        updates = {
            'state': 'pending',
            'attempts': 0,
            'error': None,
            'next_retry_at': None,
            'locked_by': None,
            'locked_at': None,
        }
        
        return self.storage.update_job(job_id, updates)
    
    def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get the next job ready to be processed
        
        Returns:
            Job dictionary or None
        """
        return self.storage.get_next_pending_job()
    
    def acquire_job(self, job_id: str, worker_id: str) -> bool:
        """Acquire a lock on a job for processing
        
        Args:
            job_id: Job ID
            worker_id: Worker identifier
            
        Returns:
            True if lock was acquired
        """
        return self.storage.acquire_job_lock(job_id, worker_id)
    
    def release_job(self, job_id: str) -> bool:
        """Release a job lock
        
        Args:
            job_id: Job ID
            
        Returns:
            True if lock was released
        """
        return self.storage.release_job_lock(job_id)
