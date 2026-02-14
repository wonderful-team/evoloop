from abc import ABC, abstractmethod
from typing import Optional
from app.core.vision.types import VisionResult, VisionTask


class VisionProvider(ABC):
    """
    Abstract base class for all vision providers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def cost_factor(self) -> float:
        """Relative cost (0 = free, 1 = expensive)."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider is currently available."""
        pass

    @abstractmethod
    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: Optional[str] = None,
        **kwargs
    ) -> VisionResult:
        """
        Process a vision task.

        Args:
            task: The type of vision task.
            image_source: Path to image or URL.
            prompt: Optional text instruction.
            **kwargs: Provider-specific arguments.

        Returns:
            VisionResult object.
        """
        pass
