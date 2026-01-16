
from abc import ABC, abstractmethod
from typing import Tuple, Optional

class Sandbox(ABC):
    """
    Abstract Base Class for Code Execution Sandboxes.
    """
    
    @abstractmethod
    def run_command(self, command: str, timeout: int = 120) -> Tuple[str, str, int]:
        """
        Run a shell command in the sandbox.
        
        Args:
            command: The command string to execute.
            timeout: Maximum execution time in seconds.
            
        Returns:
            (stdout, stderr, exit_code)
        """
        pass
    
    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        Upload a file to the sandbox.
        For Docker bind-mounts, this might be a no-op or a copy.
        """
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Download a file from the sandbox.
        """
        pass
    
    @abstractmethod
    def teardown(self) -> None:
        """
        Cleanup resources (stop containers, etc.).
        """
        pass
