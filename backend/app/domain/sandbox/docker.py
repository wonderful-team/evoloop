
import logging
import os
import docker
from typing import Tuple, Optional
from docker.errors import NotFound, APIError

from app.domain.sandbox.base import Sandbox
from app.core.config import settings

logger = logging.getLogger(__name__)

class DockerSandbox(Sandbox):
    """
    Executes commands inside a Docker container.
    """
    
    def __init__(self, image_name: str):
        self.image_name = image_name
        self.client = docker.from_env()
        self.container_name = "evoloop-sandbox-runtime"
        self.container = None
        self.cwd = "/workspace" # Default working directory inside container
        self._initialize_container()
        
    def _initialize_container(self):
        """Start or reuse the sandbox container."""
        try:
            # Check if exists
            try:
                self.container = self.client.containers.get(self.container_name)
                if self.container.status != "running":
                    self.container.start()
            except NotFound:
                # Create and start
                # Mount PROJECTS_ROOT to /workspace
                mounts = {
                    settings.PROJECTS_ROOT: {
                        "bind": "/workspace",
                        "mode": "rw"
                    }
                }
                
                logger.info(f"Starting Docker Sandbox with image {self.image_name}...")
                self.container = self.client.containers.run(
                    self.image_name,
                    command="tail -f /dev/null", # Keep alive
                    detach=True,
                    name=self.container_name,
                    volumes=mounts,
                    working_dir="/workspace",
                    auto_remove=True # Remove on stop for cleaner lifecycle? Or Persistence?
                    # Remove auto_remove if we want to restart it. 
                    # Let's keep it persistent manually.
                )
                
        except Exception as e:
            logger.error(f"Failed to initialize Docker Sandbox: {e}")
            raise

    def run_command(self, command: str, timeout: int = 120) -> Tuple[str, str, int]:
        if not self.container:
            raise RuntimeError("Sandbox container not initialized")

        command = command.strip()
        
        # 1. Handle 'cd' (Emulated)
        if command.startswith("cd "):
            path = command[3:].strip()
            # We can't actually change the container's running structure easily per exec,
            # but we can track 'cwd' for subsequent commands.
            # We need to resolve relative paths.
             # Ideally validation inside container via 'ls'.
            
            # Simple simulation:
            # Run `cd {self.cwd} && cd {path} && pwd` to get new path
            check_cmd = f"cd \"{self.cwd}\" && cd \"{path}\" && pwd"
            exit_code, output = self.container.exec_run(
                ["/bin/sh", "-c", check_cmd], 
                user="root" # Default user
            )
            
            if exit_code == 0:
                new_cwd = output.decode().strip()
                self.cwd = new_cwd
                return f"Changed directory to {self.cwd}", "", 0
            else:
                return "", f"Directory not found: {path}", 1
        
        # 2. Run Actual Command
        # We wrap in sh -c to allow chaining and env usage if needed.
        # We must execute FROM the current tracked CWD.
        full_wrapped_cmd = f"cd \"{self.cwd}\" && {command}"
        
        try:
            logger.info(f"DockerSandbox [Exec]: {full_wrapped_cmd}")
            # exec_run returns (exit_code, output_bytes)
            # Demux to separate stdout/stderr is hard with basic exec_run unless demux=True
            exit_code, output = self.container.exec_run(
                ["/bin/sh", "-c", full_wrapped_cmd],
                demux=True # Returns (stdout, stderr)
            )
            
            stdout_bytes, stderr_bytes = output if output else (None, None)
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
            
            return stdout, stderr, exit_code
            
        except Exception as e:
            logger.error(f"Docker Exec Failed: {e}")
            return "", str(e), 1

    def upload_file(self, local_path: str, remote_path: str) -> None:
        # Since we use bind-mount, if the file is in PROJECTS_ROOT, it's automatic.
        # If it's outside, we might need manual copy (put_archive).
        # For this Phase, assume working within workspace.
        pass

    def download_file(self, remote_path: str, local_path: str) -> None:
        # Bind mount handles this.
        pass

    def teardown(self) -> None:
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
            except Exception as e:
                logger.warning(f"Error tearing down sandbox: {e}")
