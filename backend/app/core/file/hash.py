"""
Hashing utilities for the File Center and beyond.
Provides consistent hashing for content and files.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


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
    content: str | bytes, algorithm: str = "md5", length: int | None = None
) -> str:
    """Compute hash with configurable algorithm and optional truncation."""
    if isinstance(content, str):
        content = content.encode("utf-8")

    hasher = hashlib.new(algorithm)
    hasher.update(content)
    result = hasher.hexdigest()

    if length:
        return result[:length]
    return result


def compute_file_hash(file_path: str, algo: str = "md5", chunk_size: int = 4096) -> str:
    """Compute hash of a file efficiently."""
    try:
        hasher = hashlib.new(algo)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, TypeError, ValueError) as e:
        logger.error(f"Failed to compute hash for {file_path}: {e}")
        return ""


def compute_version_hash(*components: str, length: int = 12) -> str:
    """Compute a version hash from multiple string components."""
    combined = "|".join(str(c) for c in components)
    return compute_hash(combined, "md5", length)


def compute_state_id(*identifiers: str, length: int = 8) -> str:
    """Compute a state identifier from multiple identifiers."""
    raw = ":".join(str(i) for i in identifiers)
    return compute_hash(raw, "md5", length)


def compute_content_hash(content: str | bytes, length: int | None = None) -> str:
    """Compute a content hash with optional truncation."""
    return compute_hash(content, "md5", length)


def sha256_digest(data: bytes) -> bytes:
    """Compute raw SHA-256 digest (returns bytes, not hex).

    For cryptographic uses such as key derivation and PKCE where the
    raw binary digest is required instead of the hex string returned by
    ``compute_sha256``.
    """
    return hashlib.sha256(data).digest()
