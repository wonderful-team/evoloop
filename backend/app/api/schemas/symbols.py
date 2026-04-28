"""API schemas for symbols routes."""

from app.api.schemas.responses import BaseAPIResponse, ListResponse
from typing import Any, Optional

class SymbolResponse(BaseAPIResponse):
    """Code symbol search result."""
    id: int
    name: str
    full_name: str
    type: str
    file_path: str
    start_line: int
    end_line: int

class SymbolWikiResponse(BaseAPIResponse):
    """Response for symbol wiki generation."""
    content: str
