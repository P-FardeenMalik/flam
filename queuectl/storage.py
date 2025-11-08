"""Storage layer for job persistence using SQLite"""

import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager


class JobStorage:
    """Handles persistent storage of jobs using SQLite"""
    
    def __init__(self, db_path: str):
        """Initialize storage
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    locked_by TEXT,
                    locked_at TEXT,
                    next_retry_at TEXT,
                    error TEXT,
                    output TEXT
                )
            ''')
            
            # Create indexes for common queries
            conn.execute('CREATE INDEX IF NOT EXISTS idx_state ON jobs(state)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_next_retry ON jobs(next_retry_at)')
    
    def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new job
        
        Args:
            job: Job dictionary with at least id and command
            
        Returns:
            Created job dictionary
        """
        now = datetime.utcnow().isoformat() + 'Z'
        
        job_data = {
            'id': job['id'],
            'command': job['command'],
            'state': job.get('state', 'pending'),
            'attempts': job.get('attempts', 0),
            'max_retries': job.get('max_retries', 3),
            'created_at': job.get('created_at', now),
            'updated_at': now,
            'locked_by': None,
            'locked_at': None,
            'next_retry_at': None,
            'error': None,
            'output': None,
        }
        
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO jobs (
                    id, command, state, attempts, max_retries,
                    created_at, updated_at, locked_by, locked_at,
                    next_retry_at, error, output
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job_data['id'], job_data['command'], job_data['state'],
                job_data['attempts'], job_data['max_retries'],
                job_data['created_at'], job_data['updated_at'],
                job_data['locked_by'], job_data['locked_at'],
                job_data['next_retry_at'], job_data['error'], job_data['output']
            ))
        
        return job_data
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID
        
        Args:
            job_id: Job ID
            
        Returns:
            Job dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
    
    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a job
        
        Args:
            job_id: Job ID
            updates: Dictionary of fields to update
            
        Returns:
            True if job was updated, False if not found
        """
        updates['updated_at'] = datetime.utcnow().isoformat() + 'Z'
        
        # Build SET clause dynamically
        set_clause = ', '.join(f'{key} = ?' for key in updates.keys())
        values = list(updates.values()) + [job_id]
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                f'UPDATE jobs SET {set_clause} WHERE id = ?',
                values
            )
            return cursor.rowcount > 0
    
    def list_jobs(self, state: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List jobs, optionally filtered by state
        
        Args:
            state: Filter by state (pending, processing, completed, failed, dead)
            limit: Maximum number of jobs to return
            
        Returns:
            List of job dictionaries
        """
        with self._get_connection() as conn:
            if state:
                cursor = conn.execute(
                    'SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC LIMIT ?',
                    (state, limit)
                )
            else:
                cursor = conn.execute(
                    'SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?',
                    (limit,)
                )
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_job_counts(self) -> Dict[str, int]:
        """Get count of jobs by state
        
        Returns:
            Dictionary mapping state to count
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT state, COUNT(*) as count FROM jobs GROUP BY state'
            )
            return {row['state']: row['count'] for row in cursor.fetchall()}
    
    def acquire_job_lock(self, job_id: str, worker_id: str) -> bool:
        """Atomically acquire a lock on a job
        
        Args:
            job_id: Job ID
            worker_id: Worker identifier
            
        Returns:
            True if lock was acquired, False otherwise
        """
        now = datetime.utcnow().isoformat() + 'Z'
        
        with self._get_connection() as conn:
            # Try to lock the job (only if not already locked)
            cursor = conn.execute('''
                UPDATE jobs 
                SET locked_by = ?, locked_at = ?, state = 'processing', updated_at = ?
                WHERE id = ? AND locked_by IS NULL AND state IN ('pending', 'failed')
            ''', (worker_id, now, now, job_id))
            
            return cursor.rowcount > 0
    
    def release_job_lock(self, job_id: str) -> bool:
        """Release a lock on a job
        
        Args:
            job_id: Job ID
            
        Returns:
            True if lock was released
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                UPDATE jobs 
                SET locked_by = NULL, locked_at = NULL, updated_at = ?
                WHERE id = ?
            ''', (datetime.utcnow().isoformat() + 'Z', job_id))
            
            return cursor.rowcount > 0
    
    def get_next_pending_job(self) -> Optional[Dict[str, Any]]:
        """Get the next pending or retryable job
        
        Returns:
            Job dictionary or None if no jobs available
        """
        now = datetime.utcnow().isoformat() + 'Z'
        
        with self._get_connection() as conn:
            # Get pending jobs or failed jobs ready for retry
            cursor = conn.execute('''
                SELECT * FROM jobs 
                WHERE locked_by IS NULL 
                AND (
                    state = 'pending' 
                    OR (state = 'failed' AND (next_retry_at IS NULL OR next_retry_at <= ?))
                )
                ORDER BY created_at ASC
                LIMIT 1
            ''', (now,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job
        
        Args:
            job_id: Job ID
            
        Returns:
            True if job was deleted
        """
        with self._get_connection() as conn:
            cursor = conn.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
            return cursor.rowcount > 0
    
    def cleanup_stale_locks(self, timeout_seconds: int = 300) -> int:
        """Clean up locks that have been held too long (worker might have crashed)
        
        Args:
            timeout_seconds: Lock timeout in seconds
            
        Returns:
            Number of locks released
        """
        from datetime import timedelta
        
        timeout_time = (datetime.utcnow() - timedelta(seconds=timeout_seconds)).isoformat() + 'Z'
        
        with self._get_connection() as conn:
            cursor = conn.execute('''
                UPDATE jobs 
                SET locked_by = NULL, locked_at = NULL, state = 'pending', updated_at = ?
                WHERE locked_by IS NOT NULL AND locked_at < ?
            ''', (datetime.utcnow().isoformat() + 'Z', timeout_time))
            
            return cursor.rowcount
