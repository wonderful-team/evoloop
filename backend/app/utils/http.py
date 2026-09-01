import httpx


def is_http_url(url: str) -> bool:
    """Whether ``url`` points at a remote HTTP(S) resource.

    Single source of truth for the repeated ``startswith(("http://", "https://"))``
    check used across file/document/video/media tooling to distinguish remote
    URLs from local paths.
    """
    return url.startswith(("http://", "https://"))


def create_client(timeout: float = 30.0, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    """
    Create a unified httpx.AsyncClient.
    Ensures consistent timeout and User-Agent.
    """
    default_headers = {
        "User-Agent": "EvoLoop/Backend",
        "Accept": "application/json"
    }
    if headers:
        default_headers.update(headers)

    return httpx.AsyncClient(
        timeout=timeout,
        headers=default_headers,
        follow_redirects=True,
        trust_env=False
    )
