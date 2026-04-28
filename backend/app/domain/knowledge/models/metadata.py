"""
Metadata models for knowledge extraction.
"""

from datetime import datetime
from typing import Any, Optional, Dict, List

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.domain.knowledge.schemas import ExtractorInfo, DocumentMetadata
