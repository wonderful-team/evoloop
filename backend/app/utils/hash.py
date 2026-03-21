import hashlib
from typing import Any


def compute_md5(content: str | bytes) -> str:
    """Compute MD5 hash of string or bytes content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.md5(content).hexdigest()


def compute_sha256(content: str | bytes) -> str:
    """Compute SHA256 hash of string or bytes content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def compute_hash(
    content: str | bytes,
    algorithm: str = "md5",
    length: int | None = None
) -> str:
    """
    Compute hash with configurable algorithm and optional truncation.
    
    Args:
        content: Content to hash
        algorithm: Hash algorithm ('md5', 'sha256', 'sha1')
        length: Optional length to truncate result
    
    Returns:
        Hex digest string, optionally truncated
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    
    hasher = hashlib.new(algorithm)
    hasher.update(content)
    result = hasher.hexdigest()
    
    if length:
        return result[:length]
    return result


def compute_file_hash(
    file_path: str,
    algo: str = "md5",
    chunk_size: int = 4096
) -> str:
    """Compute hash of a file efficiently."""
    try:
        hasher = hashlib.new(algo)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def compute_version_hash(*components: str, length: int = 12) -> str:
    """
    Compute a version hash from multiple string components.
    
    Useful for generating version identifiers from app version,
    modification time, and other version-related strings.
    
    Args:
        *components: String components to combine
        length: Length of the resulting hash
    
    Returns:
        Truncated MD5 hash
    
    Examples:
        >>> compute_version_hash("1.2.3", "1234567890")
        'a1b2c3d4e5f6'
    """
    combined = "|".join(str(c) for c in components)
    return compute_hash(combined, "md5", length)


def compute_state_id(*identifiers: str, length: int = 8) -> str:
    """
    Compute a state identifier from multiple identifiers.
    
    Args:
        *identifiers: Identifiers to combine (e.g., bundle_id, window_title)
        length: Length of the resulting hash
    
    Returns:
        Short hash suitable for state IDs
    """
    raw = ":".join(str(i) for i in identifiers)
    return compute_hash(raw, "md5", length)


def compute_content_hash(content: str | bytes, length: int | None = None) -> str:
    """
    Compute a content hash with optional truncation.
    
    Args:
        content: Content to hash
        length: Optional length to truncate
    
    Returns:
        MD5 hex digest
    """
    return compute_hash(content, "md5", length)
