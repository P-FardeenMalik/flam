"""Configuration management for QueueCTL"""

import json
import os
from pathlib import Path
from typing import Any, Dict


class Config:
    """Manages configuration for the job queue system"""
    
    DEFAULT_CONFIG = {
        'max_retries': 3,
        'backoff_base': 2,
        'db_path': 'queuectl.db',
        'worker_poll_interval': 1,  # seconds
        'worker_pid_file': '.queuectl_workers.json',
    }
    
    def __init__(self, config_dir: str = None):
        """Initialize configuration
        
        Args:
            config_dir: Directory to store config file. Defaults to ~/.queuectl
        """
        if config_dir is None:
            config_dir = os.path.join(Path.home(), '.queuectl')
        
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, 'config.json')
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        os.makedirs(self.config_dir, exist_ok=True)
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults to handle new config keys
                return {**self.DEFAULT_CONFIG, **config}
            except (json.JSONDecodeError, IOError):
                # If config is corrupted, use defaults
                return self.DEFAULT_CONFIG.copy()
        else:
            # Create default config
            config = self.DEFAULT_CONFIG.copy()
            self._save_config(config)
            return config
    
    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file"""
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value"""
        self._config[key] = value
        self._save_config(self._config)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration"""
        return self._config.copy()
    
    def get_db_path(self) -> str:
        """Get absolute path to database file"""
        db_path = self.get('db_path')
        if os.path.isabs(db_path):
            return db_path
        return os.path.join(self.config_dir, db_path)
    
    def get_worker_pid_file(self) -> str:
        """Get absolute path to worker PID file"""
        pid_file = self.get('worker_pid_file')
        if os.path.isabs(pid_file):
            return pid_file
        return os.path.join(self.config_dir, pid_file)
