"""
Build manager for cloning repositories and executing tests.
"""

import os
import subprocess
import shutil
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import threading
import selectors

import git

from .database import Database
from .models import Repository, Build


class BuildManager:
    """Manages build execution for repositories."""
    
    def __init__(self, workspace_dir: str = "workspace", db_path: str = "build_farm.db"):
        """Initialize build manager."""
        # Convert to absolute path relative to backend directory
        backend_dir = Path(__file__).parent.resolve()
        self.workspace_dir = (backend_dir / workspace_dir).resolve()
        self.workspace_dir.mkdir(exist_ok=True)
        
        # Convert db_path to absolute relative to frontend directory
        if not Path(db_path).is_absolute():
            frontend_dir = backend_dir.parent / "frontend"
            db_path = str(frontend_dir / db_path)
        
        self.db = Database(db_path)
        self._build_lock = threading.Lock()
        
        # Track running builds and termination signals
        self._running_builds = {}  # {build_id: threading.Event()}
        self._build_threads = {}   # {build_id: thread}
    
    def get_workspace_info(self) -> List[Dict]:
        """Get information about all folders in the workspace.
        
        Returns:
            List of dicts with 'name', 'size_bytes', 'size_display' keys
        """
        workspace_folders = []
        
        if not self.workspace_dir.exists():
            return workspace_folders
        
        for item in self.workspace_dir.iterdir():
            if item.is_dir():
                # Calculate folder size
                size_bytes = self._get_folder_size(item)
                size_display = self._format_size(size_bytes)
                
                workspace_folders.append({
                    'name': item.name,
                    'path': str(item),
                    'size_bytes': size_bytes,
                    'size_display': size_display
                })
        
        # Sort by size descending
        workspace_folders.sort(key=lambda x: x['size_bytes'], reverse=True)
        return workspace_folders
    
    def _get_folder_size(self, folder: Path) -> int:
        """Recursively calculate folder size in bytes."""
        total = 0
        try:
            for item in folder.rglob('*'):
                if item.is_file():
                    total += item.stat().st_size
        except (PermissionError, OSError):
            pass
        return total
    
    def _format_size(self, size_bytes: int) -> str:
        """Format size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    def cleanup_workspace(self) -> Tuple[int, int, str]:
        """Delete all folders in workspace except those with running builds.
        
        Returns:
            Tuple of (deleted_count, kept_count, message)
        """
        if not self.workspace_dir.exists():
            return 0, 0, "Workspace directory does not exist"
        
        # Get all running builds from database
        running_builds = self.db.get_builds_by_status('running')
        running_workspaces = {build.workspace_name for build in running_builds if build.workspace_name}
        
        deleted_count = 0
        kept_count = 0
        errors = []
        
        for item in self.workspace_dir.iterdir():
            # Skip if it's a file (like placeholder.txt)
            if item.is_file():
                continue
            
            # Skip if it's a running build's workspace
            if item.name in running_workspaces:
                kept_count += 1
                continue
            
            # Delete the folder using sudo (configured in sudoers for passwordless access)
            try:
                result = subprocess.run(
                    ['sudo', 'rm', '-rf', str(item)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0:
                    deleted_count += 1
                else:
                    errors.append(f"Failed to delete {item.name}: {result.stderr}")
            except subprocess.TimeoutExpired:
                errors.append(f"Failed to delete {item.name}: Operation timed out")
            except Exception as e:
                errors.append(f"Failed to delete {item.name}: {str(e)}")
        
        message = f"Deleted {deleted_count} folder(s), kept {kept_count} running build(s)"
        if errors:
            message += f"\n\nErrors:\n" + "\n".join(errors)
        
        return deleted_count, kept_count, message
    
    def clone_repository(self, repo: Repository, target_dir: Path) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Clone a repository to the target directory.
        
        Returns:
            Tuple of (success, message, commit_hash, commit_message)
        """
        try:
            # Remove existing directory if it exists
            if target_dir.exists():
                shutil.rmtree(target_dir)
            
            # Set SSH options via environment for GitPython
            env = os.environ.copy()
            env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=~/.ssh/known_hosts'
            
            # Clone the repository with custom environment
            with git.Git().custom_environment(**env):
                repo_obj = git.Repo.clone_from(
                    repo.git_url,
                    target_dir,
                    branch=repo.branch
                )
            
            # Get commit information
            commit = repo_obj.head.commit
            commit_hash = commit.hexsha[:8]  # Short hash
            commit_message = commit.message.strip().split('\n')[0]  # First line only
            
            return True, f"Successfully cloned {repo.name}", commit_hash, commit_message
            
        except git.GitCommandError as e:
            return False, f"Git error: {str(e)}", None, None
        except Exception as e:
            return False, f"Clone failed: {str(e)}", None, None
    
    def run_test_script(self, repo_dir: Path, build_id: int, base_logs: str, termination_event: threading.Event) -> Tuple[bool, str, int, float, Optional[List[Dict]]]:
        """
        Execute the run_test.sh script in the repository.
        
        Returns:
            Tuple of (success, logs, exit_code, duration, test_results)
        """
        test_script = repo_dir / "run_test.sh"
        
        if not test_script.exists():
            return False, "Error: run_test.sh not found in repository", -1, 0.0, None
        
        # Make script executable
        test_script.chmod(0o755)
        
        try:
            # Track start time
            start_time = time.time()
            
            # Execute the test script with streaming output
            process = subprocess.Popen(
                ["bash", str(test_script)],
                cwd=repo_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Immediately update to show script started
            start_log = f"{base_logs}=== STDOUT (live) ===\n[Script started, waiting for output...]\n"
            self.db.update_build_logs(build_id, start_log)
            
            stdout_lines: List[str] = []
            stderr_lines: List[str] = []
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stderr, selectors.EVENT_READ)
            
            last_update = time.monotonic()
            terminated = False
            
            timeout_seconds = 3600  # 1 hour timeout
            timed_out = False
            while True:
                if (time.time() - start_time) > timeout_seconds:
                    timed_out = True
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    break
                if termination_event.is_set() and not terminated:
                    terminated = True
                    try:
                        process.terminate()
                    except Exception:
                        pass
                
                events = selector.select(timeout=0.2)
                for key, _ in events:
                    line = key.fileobj.readline()
                    if line:
                        if key.fileobj is process.stdout:
                            stdout_lines.append(line)
                        else:
                            stderr_lines.append(line)
                    else:
                        selector.unregister(key.fileobj)
                        try:
                            key.fileobj.close()
                        except Exception:
                            pass
                
                now = time.monotonic()
                if (stdout_lines and (now - last_update) >= 0.5) or (now - last_update) >= 2.0:
                    live_stdout = "".join(stdout_lines)
                    # Show last 50 lines for better performance
                    stdout_preview = "\n".join(live_stdout.splitlines()[-50:])
                    live_logs = f"{base_logs}=== STDOUT (live) ===\n{stdout_preview}"
                    self.db.update_build_logs(build_id, live_logs)
                    last_update = now
                
                if process.poll() is not None and not selector.get_map():
                    break
            
            # Ensure process is terminated if requested
            if terminated and process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
            if timed_out and process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
            
            exit_code = process.wait()
            duration = time.time() - start_time
            
            # Combine stdout and stderr - return WITHOUT base_logs (it gets appended by caller)
            stdout_text = "".join(stdout_lines)
            stderr_text = "".join(stderr_lines)
            
            # Show last 100 lines of stdout and all stderr in final logs
            stdout_lines_list = stdout_text.splitlines()
            if len(stdout_lines_list) > 100:
                stdout_display = "\n".join(stdout_lines_list[-100:])
                stdout_display = f"... (showing last 100 of {len(stdout_lines_list)} lines)\n\n" + stdout_display
            else:
                stdout_display = stdout_text
            
            logs = f"=== STDOUT ===\n{stdout_display}\n\n=== STDERR ===\n{stderr_text}"
            if timed_out:
                logs = f"{logs}\n\nError: Test script timed out after 1 hour"
                return False, logs, -2, duration, None
            
            # Try to read and validate test results JSON file
            test_results = None
            json_validation_failed = False
            results_file = repo_dir / "test_results.json"
            
            if results_file.exists():
                try:
                    with open(results_file, 'r') as f:
                        test_results = json.load(f)
                    
                    # Validate JSON structure
                    if not isinstance(test_results, list):
                        logs += f"\n\nError: test_results.json must be a JSON array, got {type(test_results).__name__}"
                        json_validation_failed = True
                        test_results = None
                    else:
                        # Validate each test result entry
                        for idx, test in enumerate(test_results):
                            if not isinstance(test, dict):
                                logs += f"\n\nError: test_results.json[{idx}] must be an object, got {type(test).__name__}"
                                json_validation_failed = True
                                test_results = None
                                break
                            
                            if 'name' not in test:
                                logs += f"\n\nError: test_results.json[{idx}] missing required field 'name'"
                                json_validation_failed = True
                                test_results = None
                                break
                            
                            if 'success' not in test:
                                logs += f"\n\nError: test_results.json[{idx}] missing required field 'success'"
                                json_validation_failed = True
                                test_results = None
                                break
                            
                            if not isinstance(test['success'], bool):
                                logs += f"\n\nError: test_results.json[{idx}].success must be boolean, got {type(test['success']).__name__}"
                                json_validation_failed = True
                                test_results = None
                                break
                        
                        if not json_validation_failed and test_results:
                            logs += f"\n\n✓ Successfully parsed {len(test_results)} test result(s) from test_results.json"
                
                except json.JSONDecodeError as e:
                    logs += f"\n\nError: Failed to parse test_results.json - Invalid JSON syntax: {e}"
                    json_validation_failed = True
                except Exception as e:
                    logs += f"\n\nError: Failed to read test_results.json: {e}"
                    json_validation_failed = True
            
            # Determine success: script must exit 0 AND JSON must be valid (if present)
            if exit_code == 0 and not json_validation_failed:
                success = True
            else:
                success = False
                # If JSON validation failed, override exit code
                if json_validation_failed and exit_code == 0:
                    logs += "\n\nTest marked as FAILED due to invalid test_results.json"
                    return False, logs, -4, duration, None  # -4 = JSON validation error
            
            return success, logs, exit_code, duration, test_results
            
        except subprocess.TimeoutExpired:
            duration = 3600.0  # Timeout duration
            return False, "Error: Test script timed out after 1 hour", -2, duration, None
        except Exception as e:
            return False, f"Error executing test script: {str(e)}", -3, 0.0, None
    
    def execute_build(self, repo_id: int, build_id: int):
        """
        Execute a build for a repository.
        This is the main build workflow.
        """
        try:
            # Create termination signal for this build
            self._running_builds[build_id] = threading.Event()
            
            # Get repository info
            repo = self.db.get_repository(repo_id)
            if not repo:
                self.db.update_build_status(
                    build_id,
                    'error',
                    logs="Error: Repository not found",
                    end_time=datetime.now()
                )
                return
            
            # Update status to running
            self.db.update_build_status(
                build_id,
                'running',
                start_time=datetime.now()
            )
            
            # Create workspace directory for this build
            build_dir = self.workspace_dir / f"{repo.name}_{build_id}"
            
            # Check if termination was requested
            if self._running_builds[build_id].is_set():
                self.db.update_build_status(
                    build_id,
                    'terminated',
                    logs="Build terminated by user",
                    end_time=datetime.now()
                )
                # Cleanup workspace directory
                try:
                    if build_dir.exists():
                        shutil.rmtree(build_dir)
                except Exception as e:
                    print(f"Warning: Failed to cleanup build directory: {e}")
                return
            
            # Clone repository
            success, message, commit_hash, commit_message = self.clone_repository(repo, build_dir)
            
            if not success:
                self.db.update_build_status(
                    build_id,
                    'error',
                    logs=message,
                    end_time=datetime.now()
                )
                # Cleanup workspace directory
                try:
                    if build_dir.exists():
                        shutil.rmtree(build_dir)
                except Exception as e:
                    print(f"Warning: Failed to cleanup build directory: {e}")
                return
            
            # Check if termination was requested
            if self._running_builds[build_id].is_set():
                self.db.update_build_status(
                    build_id,
                    'terminated',
                    logs=f"Clone: {message}\nBuild terminated by user before testing",
                    end_time=datetime.now()
                )
                # Cleanup workspace directory
                try:
                    if build_dir.exists():
                        shutil.rmtree(build_dir)
                except Exception as e:
                    print(f"Warning: Failed to cleanup build directory: {e}")
                return
            
            # Update with commit info
            logs = f"Clone: {message}\nCommit: {commit_hash}\n{commit_message}\n\n"
            self.db.update_build_status(
                build_id,
                'running',
                logs=f"{logs}=== STDOUT (live) ===\n"
            )
            
            # Run test script (streaming)
            test_success, test_logs, exit_code, test_duration, test_results = self.run_test_script(
                build_dir,
                build_id,
                logs,
                self._running_builds[build_id]
            )
            logs += test_logs
            
            # Check if termination was requested
            if self._running_builds[build_id].is_set():
                self.db.update_build_status(
                    build_id,
                    'terminated',
                    logs=logs,
                    commit_hash=commit_hash,
                    commit_message=commit_message,
                    end_time=datetime.now()
                )
                # Cleanup workspace directory
                try:
                    if build_dir.exists():
                        shutil.rmtree(build_dir)
                except Exception as e:
                    print(f"Warning: Failed to cleanup build directory: {e}")
                return
            
            # Convert test_results to JSON string if present
            test_results_json = None
            if test_results:
                try:
                    test_results_json = json.dumps(test_results)
                except Exception as e:
                    logs += f"\n\nWarning: Failed to serialize test results: {e}"
            
            # Determine final status
            if test_success:
                status = 'success'
            else:
                status = 'failed'
            
            # Update build with final results
            self.db.update_build_status(
                build_id,
                status,
                commit_hash=commit_hash,
                commit_message=commit_message,
                logs=logs,
                exit_code=exit_code,
                test_duration=test_duration,
                test_results=test_results_json,
                end_time=datetime.now()
            )
            
            # Cleanup: Remove build directory
            try:
                shutil.rmtree(build_dir)
            except Exception as e:
                print(f"Warning: Failed to cleanup build directory: {e}")
                
        except Exception as e:
            # Handle unexpected errors
            self.db.update_build_status(
                build_id,
                'error',
                logs=f"Unexpected error: {str(e)}",
                end_time=datetime.now()
            )
            # Cleanup workspace directory
            try:
                if build_dir.exists():
                    shutil.rmtree(build_dir)
            except Exception as cleanup_error:
                print(f"Warning: Failed to cleanup build directory: {cleanup_error}")
        finally:
            # Clean up termination signal
            if build_id in self._running_builds:
                del self._running_builds[build_id]
            if build_id in self._build_threads:
                del self._build_threads[build_id]
    
    def start_build(self, repo_id: int) -> int:
        """
        Start a new build for a repository.
        Runs in a background thread.
        
        Returns:
            Build ID
        """
        # Create build entry
        build_id = self.db.create_build(repo_id)
        
        # Start build in background thread
        thread = threading.Thread(
            target=self.execute_build,
            args=(repo_id, build_id),
            daemon=True
        )
        self._build_threads[build_id] = thread
        thread.start()
        
        return build_id
    
    def terminate_build(self, build_id: int) -> bool:
        """
        Terminate a running build.
        Returns True if termination signal was sent, False if build not running.
        """
        if build_id in self._running_builds:
            self._running_builds[build_id].set()
            return True
        return False
    
    def get_running_builds_count(self) -> int:
        """Get count of currently running builds."""
        builds = self.db.get_recent_builds(limit=100)
        return sum(1 for b in builds if b.status == 'running')
