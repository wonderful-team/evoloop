import hashlib


def compute_md5(content: str) -> str:
    """Compute MD5 hash of string content."""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def compute_sha256(content: str) -> str:
    """Compute SHA256 hash of string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_file_hash(file_path: str, algo: str = "md5", chunk_size: int = 4096) -> str:
    """Compute hash of a file efficiently."""
    if algo == "md5":
        hasher = hashlib.md5()
    elif algo == "sha256":
        hasher = hashlib.sha256()
    else:
        raise ValueError("Unsupported algorithm")

    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""
