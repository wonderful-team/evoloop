"""
TTS Provider Base Classes
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TTSOptions:
    text: str
    voice: str = "中文女"
    speed: float = 1.0


@dataclass
class TTSResult:
    audio_bytes: bytes
    sample_rate: int = 22050


class BaseTTSProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def load_model(self) -> None:
        ...

    @abstractmethod
    async def generate(self, options: TTSOptions) -> TTSResult:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def list_voices(self) -> list[str]:
        ...
