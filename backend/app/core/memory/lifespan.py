"""
Memory System Lifespan Management

Provides application-level lifecycle management for the memory system.
This ensures a single MemoryContainer instance is created at app startup
and properly shutdown at app exit.

Usage:
    # In main.py or application entry point
    from app.core.memory.lifespan import memory_lifespan
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with memory_lifespan(app):
            yield
    
    app = FastAPI(lifespan=lifespan)

    # In routes or services
    from app.core.memory.lifespan import get_memory_manager
    
    manager = get_memory_manager()
    await manager.save_memory(entry)
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

from fastapi import FastAPI

from app.core.memory.config import MemoryConfig
from app.core.memory.container import MemoryContainer
from app.core.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class MemoryLifespanManager:
    """
    Manages the lifecycle of the MemoryContainer at application level.
    
    This ensures:
    1. Single container instance per application
    2. Proper initialization at startup
    3. Graceful shutdown at exit
    4. Thread-safe access
    """
    
    _instance: Optional[MemoryContainer] = None
    _config: Optional[MemoryConfig] = None
    _lock = asyncio.Lock()
    
    @classmethod
    def initialize(cls, config: Optional[MemoryConfig] = None) -> MemoryContainer:
        """
        Initialize the global memory container.
        
        Args:
            config: Memory configuration. Uses MemoryConfig.from_settings() if None.
            
        Returns:
            The initialized MemoryContainer instance
            
        Raises:
            RuntimeError: If already initialized
        """
        if cls._instance is not None:
            raise RuntimeError("MemoryContainer already initialized. Call shutdown() first.")
        
        cls._config = config or MemoryConfig.from_settings()
        cls._instance = MemoryContainer(cls._config)
        
        # Note: We don't call initialize() here because it's async
        # Use ainit() for async initialization
        return cls._instance
    
    @classmethod
    async def ainitialize(cls, config: Optional[MemoryConfig] = None) -> MemoryContainer:
        """
        Async initialize the global memory container.
        """
        if cls._instance is not None:
            # If already set, check if it's actually finished initializing
            if cls._instance._initialized:
                return cls._instance
            # Wait for it (this is a simple spin wait, better would be a lock)
            # For now, let's just use a lock
            
        async with cls._lock:
            if cls._instance is not None:
                if not cls._instance._initialized:
                    await cls._instance.initialize()
                return cls._instance
                
            cls._config = config or MemoryConfig.from_settings()
            cls._instance = MemoryContainer(cls._config)
            await cls._instance.initialize()
            logger.info("[MemoryLifespan] MemoryContainer initialized")
            return cls._instance
    
    @classmethod
    async def shutdown(cls) -> None:
        """
        Shutdown the global memory container.
        
        This should be called at application exit.
        """
        if cls._instance is not None:
            try:
                await cls._instance.shutdown()
                logger.info("[MemoryLifespan] MemoryContainer shutdown")
            except Exception as e:
                logger.error(f"[MemoryLifespan] Error during shutdown: {e}")
            finally:
                cls._instance = None
                cls._config = None
    
    @classmethod
    def get_container(cls) -> MemoryContainer:
        """
        Get the global memory container.
        
        Returns:
            The MemoryContainer instance
            
        Raises:
            RuntimeError: If not initialized
        """
        if cls._instance is None:
            raise RuntimeError(
                "MemoryContainer not initialized. "
                "Call MemoryLifespanManager.ainitialize() first."
            )
        return cls._instance
    
    @classmethod
    def get_manager(cls) -> MemoryManager:
        """
        Get the global memory manager.
        
        This is a convenience method to get the manager directly.
        
        Returns:
            The MemoryManager instance
            
        Raises:
            RuntimeError: If not initialized
        """
        return cls.get_container().memory_manager
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the memory container is fully initialized."""
        return cls._instance is not None and cls._instance._initialized


# Convenience functions for direct import

def get_memory_container() -> MemoryContainer:
    """Get the global memory container."""
    return MemoryLifespanManager.get_container()


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager."""
    return MemoryLifespanManager.get_manager()


# FastAPI lifespan context manager

@asynccontextmanager
async def memory_lifespan(app: Optional[FastAPI] = None) -> AsyncGenerator[MemoryContainer, None]:
    """
    FastAPI lifespan context manager for memory system.
    
    Usage:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with memory_lifespan(app):
                yield
        
        app = FastAPI(lifespan=lifespan)
    
    Args:
        app: Optional FastAPI application instance
        
    Yields:
        The initialized MemoryContainer
    """
    container = await MemoryLifespanManager.ainitialize()
    try:
        yield container
    finally:
        await MemoryLifespanManager.shutdown()


# Legacy compatibility alias
# This allows old code to work during migration
async def get_container() -> MemoryContainer:
    """
    Legacy compatibility function.
    
    Returns the global container, initializing if necessary.
    
    Note: This is for backward compatibility. New code should use
    MemoryLifespanManager.get_container() or get_memory_container().
    """
    if not MemoryLifespanManager.is_initialized():
        logger.warning(
            "[MemoryLifespan] Lazy initialization is deprecated. "
            "Use MemoryLifespanManager.ainitialize() at app startup."
        )
        await MemoryLifespanManager.ainitialize()
    return MemoryLifespanManager.get_container()
