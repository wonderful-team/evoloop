import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

# Optional imports
try:
    import jwt
    from passlib.context import CryptContext
    HAS_JWT = True
except ImportError:
    HAS_JWT = False
    jwt = None  # type: ignore[assignment]

# Try to import settings, fallback if not available
try:
    from app.core.config import settings
    HAS_SETTINGS = True
except (ImportError, Exception):
    # Exception covers Pydantic validation errors in test environment
    HAS_SETTINGS = False
    settings = None  # type: ignore[assignment]

if HAS_JWT:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
else:
    pwd_context = None

ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    if not HAS_JWT or not HAS_SETTINGS:
        raise ImportError("JWT and settings are required for token creation")
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not HAS_JWT:
        raise ImportError("passlib is required for password verification")
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    if not HAS_JWT:
        raise ImportError("passlib is required for password hashing")
    return pwd_context.hash(password)


def generate_hmac_signature(secret: str, message: str, hash_alg=hashlib.sha256) -> str:
    """
    Generate HMAC signature for a message.
    Used for API request signing (e.g. EvoCloud).
    """
    if not secret:
        return ""
    return hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hash_alg
    ).hexdigest()


# ============================================================================
# Path Security
# ============================================================================


def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """
    Sanitize a filename by removing or replacing unsafe characters.
    
    Args:
        filename: Original filename
        replacement: Character to replace unsafe characters with
    
    Returns:
        Sanitized filename safe for use in filesystem
    """
    # Remove path separators and null bytes
    unsafe = ['\\', '/', '\x00', '\n', '\r', '\t']
    result = filename
    for char in unsafe:
        result = result.replace(char, replacement)

    # Remove other special characters
    result = re.sub(r'[<>:"|?*]', replacement, result)

    # Limit length
    if len(result) > 255:
        name, ext = os.path.splitext(result)
        result = name[:255 - len(ext)] + ext

    # Don't allow hidden files or reserved names on Windows
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3',
                'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}

    base = os.path.splitext(result)[0].upper()
    if base in reserved:
        result = replacement + result

    return result


def is_path_within_base(base_path: str, target_path: str) -> bool:
    """
    Check if target_path is within base_path (prevents directory traversal).
    
    Args:
        base_path: Base directory path
        target_path: Path to check
    
    Returns:
        True if target_path is within base_path
    """
    from pathlib import Path
    try:
        base = Path(base_path).resolve()
        target = Path(target_path).resolve()
        return str(target).startswith(str(base))
    except (ValueError, OSError):
        return False


# ============================================================================
# Input Validation
# ============================================================================


def validate_bundle_id(bundle_id: str) -> bool:
    """
    Validate Android/iOS bundle ID format.
    
    Args:
        bundle_id: Bundle identifier (e.g., 'com.example.app')
    
    Returns:
        True if valid bundle ID format
    """
    import re
    # Bundle ID format: com.company.app (reverse domain notation)
    pattern = r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$'
    return bool(re.match(pattern, bundle_id))


def validate_package_name(name: str) -> bool:
    """
    Validate Android package name.
    
    Args:
        name: Package name
    
    Returns:
        True if valid package name
    """
    import re
    # Package name: com.company.app, must start with letter, lowercase preferred
    pattern = r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'
    return bool(re.match(pattern, name))


def is_safe_url(url: str, allowed_schemes: set[str] | None = None) -> bool:
    """
    Check if URL is safe (no file://, javascript:, etc.).
    
    Args:
        url: URL to check
        allowed_schemes: Set of allowed schemes (default: http, https)
    
    Returns:
        True if URL appears safe
    """
    if allowed_schemes is None:
        allowed_schemes = {'http', 'https'}
    
    # Check for dangerous schemes
    dangerous_schemes = {'javascript:', 'data:', 'vbscript:', 'file:'}
    lower_url = url.lower().strip()
    
    for scheme in dangerous_schemes:
        if lower_url.startswith(scheme):
            return False
    
    # If URL has a scheme, verify it's allowed
    if '://' in url:
        scheme = url.split('://')[0].lower()
        if scheme not in allowed_schemes:
            return False
    
    return True


# ============================================================================
# Data Sanitization
# ============================================================================


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """
    Sanitize a string value for safe storage/display.
    
    Args:
        value: String to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    """
    # Remove control characters except common whitespace
    sanitized = ''.join(char for char in value if char >= ' ' or char in '\t\n\r')
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive data showing only last few characters.
    
    Args:
        data: Sensitive data string
        visible_chars: Number of characters to show at end
    
    Returns:
        Masked string (e.g., '****1234')
    """
    if len(data) <= visible_chars:
        return '*' * len(data)
    
    return '*' * (len(data) - visible_chars) + data[-visible_chars:]


# ============================================================================
# Rate Limiting (Simple)
# ============================================================================


class SimpleRateLimiter:
    """
    Simple in-memory rate limiter.
    
    Example:
        limiter = SimpleRateLimiter(max_calls=10, period=60)
        if limiter.is_allowed("user_123"):
            process_request()
        else:
            raise RateLimitExceeded()
    """
    
    def __init__(self, max_calls: int, period: float):
        """
        Initialize rate limiter.
        
        Args:
            max_calls: Maximum number of calls allowed
            period: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self._calls: dict[str, list[float]] = {}
    
    def is_allowed(self, key: str) -> bool:
        """
        Check if call is allowed for key.
        
        Args:
            key: Identifier (e.g., user ID, IP address)
        
        Returns:
            True if call is allowed
        """
        import time
        
        now = time.time()
        
        # Get or create call history
        calls = self._calls.get(key, [])
        
        # Remove old calls outside the period
        calls = [t for t in calls if now - t < self.period]
        
        # Check if under limit
        if len(calls) < self.max_calls:
            calls.append(now)
            self._calls[key] = calls
            return True
        
        self._calls[key] = calls
        return False
    
    def get_remaining(self, key: str) -> int:
        """Get remaining calls for key."""
        import time
        
        now = time.time()
        calls = self._calls.get(key, [])
        calls = [t for t in calls if now - t < self.period]
        return max(0, self.max_calls - len(calls))
    
    def reset(self, key: str) -> None:
        """Reset rate limit for key."""
        self._calls.pop(key, None)
    
    def clear(self) -> None:
        """Clear all rate limits."""
        self._calls.clear()
