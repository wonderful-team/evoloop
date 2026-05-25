"""Memory storage exceptions."""


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class StorageNotFoundError(StorageError):
    """Raised when a memory entry is not found."""
    pass


class StorageConnectionError(StorageError):
    """Raised when connection to storage backend fails."""
    pass
