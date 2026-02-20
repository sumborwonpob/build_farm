"""
Database operations for the build farm system using SQLite.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from contextlib import contextmanager

from .models import Repository, Build


class Database:
    """SQLite database manager for build farm."""
    
    def __init__(self, db_path: str = "build_farm.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
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
    
    def _init_database(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create repositories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    git_url TEXT NOT NULL,
                    branch TEXT NOT NULL DEFAULT 'main',
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create builds table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS builds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    commit_hash TEXT,
                    commit_message TEXT,
                    logs TEXT,
                    exit_code INTEGER,
                    test_duration REAL,
                    test_results TEXT,
                    FOREIGN KEY (repo_id) REFERENCES repositories (id) ON DELETE CASCADE
                )
            """)
            
            # Create index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_builds_repo_id 
                ON builds(repo_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_builds_status 
                ON builds(status)
            """)
    
    # Repository operations
    def add_repository(self, name: str, git_url: str, branch: str = "main", 
                      description: str = None) -> int:
        """Add a new repository configuration."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO repositories (name, git_url, branch, description)
                VALUES (?, ?, ?, ?)
            """, (name, git_url, branch, description))
            return cursor.lastrowid
    
    def get_repository(self, repo_id: int) -> Optional[Repository]:
        """Get repository by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,))
            row = cursor.fetchone()
            if row:
                return Repository(
                    id=row['id'],
                    name=row['name'],
                    git_url=row['git_url'],
                    branch=row['branch'],
                    description=row['description'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                )
            return None
    
    def get_all_repositories(self) -> List[Repository]:
        """Get all repositories."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories ORDER BY name")
            return [
                Repository(
                    id=row['id'],
                    name=row['name'],
                    git_url=row['git_url'],
                    branch=row['branch'],
                    description=row['description'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                )
                for row in cursor.fetchall()
            ]
    
    def delete_repository(self, repo_id: int):
        """Delete a repository and all its builds."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
    
    # Build operations
    def create_build(self, repo_id: int) -> int:
        """Create a new build entry with pending status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO builds (repo_id, status, start_time)
                VALUES (?, 'pending', ?)
            """, (repo_id, datetime.now().isoformat()))
            return cursor.lastrowid
    
    def update_build_status(self, build_id: int, status: str, **kwargs):
        """Update build status and optional fields."""
        fields = []
        values = []
        
        fields.append("status = ?")
        values.append(status)
        
        for key, value in kwargs.items():
            if key in ['start_time', 'end_time', 'commit_hash', 'commit_message', 
                      'logs', 'exit_code', 'test_duration', 'test_results']:
                fields.append(f"{key} = ?")
                if isinstance(value, datetime):
                    values.append(value.isoformat())
                else:
                    values.append(value)
        
        values.append(build_id)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE builds 
                SET {', '.join(fields)}
                WHERE id = ?
            """, values)

    def update_build_logs(self, build_id: int, logs: str):
        """Update only the logs for a build without changing status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE builds SET logs = ? WHERE id = ?", (logs, build_id))
    
    def get_build(self, build_id: int) -> Optional[Build]:
        """Get build by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM builds WHERE id = ?", (build_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_build(row)
            return None
    
    def get_builds_for_repo(self, repo_id: int, limit: int = 50) -> List[Build]:
        """Get recent builds for a repository."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM builds 
                WHERE repo_id = ? 
                ORDER BY start_time DESC 
                LIMIT ?
            """, (repo_id, limit))
            return [self._row_to_build(row) for row in cursor.fetchall()]
    
    def get_recent_builds(self, limit: int = 50) -> List[Build]:
        """Get recent builds across all repositories."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM builds 
                ORDER BY start_time DESC 
                LIMIT ?
            """, (limit,))
            return [self._row_to_build(row) for row in cursor.fetchall()]
    
    def get_all_builds(self) -> List[Build]:
        """Get all builds without limit."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM builds 
                ORDER BY start_time DESC
            """)
            return [self._row_to_build(row) for row in cursor.fetchall()]
    
    def get_builds_by_status(self, status: str) -> List[Build]:
        """Get all builds with a specific status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM builds 
                WHERE status = ?
                ORDER BY start_time DESC
            """, (status,))
            return [self._row_to_build(row) for row in cursor.fetchall()]
    
    def get_latest_build_for_repo(self, repo_id: int) -> Optional[Build]:
        """Get the most recent build for a repository."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM builds 
                WHERE repo_id = ? 
                ORDER BY start_time DESC 
                LIMIT 1
            """, (repo_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_build(row)
            return None

    def get_latest_running_build(self) -> Optional[Build]:
        """Get the most recent running build."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM builds
                WHERE status = 'running'
                ORDER BY start_time DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return self._row_to_build(row)
            return None

    def clear_build_history_for_repo(self, repo_id: int):
        """Delete all builds for a repository."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM builds WHERE repo_id = ?", (repo_id,))
    
    def cleanup_stale_running_builds(self):
        """Mark any 'running' builds as 'error' (for when service crashed/restarted)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE builds 
                SET status = 'error', logs = COALESCE(logs, '') || '\n\nMarked as error on service restart - build may have been interrupted'
                WHERE status = 'running'
            """)
    
    def factory_reset(self):
        """Factory reset: delete all data and reinitialize the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Drop all tables
            cursor.execute("DROP TABLE IF EXISTS builds")
            cursor.execute("DROP TABLE IF EXISTS repositories")
        # Reinitialize the database schema
        self._init_database()
    
    def _row_to_build(self, row: sqlite3.Row) -> Build:
        """Convert database row to Build object."""
        return Build(
            id=row['id'],
            repo_id=row['repo_id'],
            status=row['status'],
            start_time=datetime.fromisoformat(row['start_time']) if row['start_time'] else None,
            end_time=datetime.fromisoformat(row['end_time']) if row['end_time'] else None,
            commit_hash=row['commit_hash'],
            commit_message=row['commit_message'],
            logs=row['logs'],
            exit_code=row['exit_code'],
            test_duration=row['test_duration'],
            test_results=row['test_results']
        )
