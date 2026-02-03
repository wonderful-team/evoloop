"""
Abstract Base Classes for Brain Drivers.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseBrainDriver(ABC):
    """
    Interface for a computation unit (Brain).
    Can be an SSM (Fast) or an LLM (Slow).
    """
    
    @abstractmethod
    async def generate(self, context: str, user_input: str, system_prompt: Optional[str] = None) -> str:
        """
        Generates a text response based on context.
        """
        pass
        
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Returns True if the driver is ready.
        """
        pass
