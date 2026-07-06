"""Schemas for atlas module."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.infrastructure.pydantic_base import DynamicBaseModel


class AtlasStateMetadata(DynamicBaseModel):
    screenshot_hash: str | None = None
    platform_version: str | None = None
    app_tags: list[str] = Field(default_factory=list)


class MenuItem(DynamicBaseModel):
    label: str
    action: str | None = None
    children: list[MenuItem] = Field(default_factory=list)


class MenuTree(DynamicBaseModel):
    menus: list[MenuItem] = Field(default_factory=list)


class Rect(BaseModel):
    """Represents a rectangular area in UI coordinates."""
    x: int
    y: int
    width: int
    height: int

    @model_validator(mode="before")
    @classmethod
    def from_list(cls, data: Any) -> Any:
        """Support [x, y, width, height] list format."""
        if isinstance(data, (list, tuple)) and len(data) == 4:
            return {
                "x": data[0],
                "y": data[1],
                "width": data[2],
                "height": data[3]
            }
        return data


class ElementMetadata(DynamicBaseModel):
    """Platform-specific metadata for a UI element."""
    model_config = ConfigDict(populate_by_name=True)

    # Common cross-platform attributes
    class_name: str | None = Field(None, alias="class")
    resource_id: str | None = None

    # Android specific
    package_name: str | None = None
    content_desc: str | None = None
    checkable: bool = False
    checked: bool = False
    scrollable: bool = False

    # MacOS specific
    ax_identifier: str | None = None
    ax_role: str | None = None
    ax_subrole: str | None = None

    # Catch-all for additional attributes
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def capture_extra(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        # Identify known fields (including aliases)
        known_fields = {f.alias or name for name, f in cls.model_fields.items()}

        extra = values.get("extra", {})
        for k, v in list(values.items()):
            if k not in known_fields and k != "extra":
                extra[k] = values.pop(k)

        values["extra"] = extra
        return values


class AtlasAppSummary(DynamicBaseModel):
    """Summary of an Atlas app for LLM context generation."""
    app_name: str
    bundle_id: str
    platform: str
    version_hash: str = ""
    state_count: int = 0
    states: list = []


class AtlasStateDetail(DynamicBaseModel):
    """Detailed information about a specific UI state."""
    state_id: str
    window_title: str | None = None
    elements: list = []


class AtlasAppInfo(DynamicBaseModel):
    """Lightweight info for a mapped app."""
    app_name: str
    bundle_id: str
    platform: str
