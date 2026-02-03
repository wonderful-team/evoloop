class BrainException(Exception):
    """Base exception for brain module."""
    pass

class MemoryAccessViolation(BrainException):
    """Raised when trying to access files outside the sandbox."""
    pass

class DriverError(BrainException):
    """Raised when a model driver fails."""
    pass
