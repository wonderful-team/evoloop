import httpx
from typing import Optional, Dict

def create_client(timeout: float = 30.0, headers: Optional[Dict[str, str]] = None) -> httpx.AsyncClient:
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
        follow_redirects=True
    )
