"""Pydantic schemas for the AppMap five-layer payload (LLM output contract)."""

from __future__ import annotations

from pydantic import Field, field_validator

from app.infrastructure.pydantic_base import DynamicBaseModel

ACTION_KINDS = ("read", "write")
RISK_TIERS = ("ui", "data", "money")
SELECTOR_TYPES = ("id", "name", "class", "css", "lay-filter", "text", "data-attr")


class AppMapRoute(DynamicBaseModel):
    name: str
    url: str
    method: str = "GET"
    source_action: str | None = None


class AppMapAction(DynamicBaseModel):
    name: str
    kind: str
    risk_tier: str
    business_rule: str = ""
    touches_tables: list[str] = Field(default_factory=list)
    set_fields: list[str] = Field(default_factory=list)
    pk: str | None = None
    controller: str | None = None
    line: int | None = None


class AppMapElement(DynamicBaseModel):
    name: str
    page: str | None = None
    line: int | None = None
    binds: str = ""
    # How `name` appears in the view markup (id= / name= / class / lay-filter /
    # css selector / visible text). None means the collector could not tell;
    # templates fall back to a "#name, [name='name']" union guess.
    selector_type: str | None = None

    @field_validator("binds", mode="before")
    @classmethod
    def _coerce_binds(cls, v):
        # LLMs naturally emit binds as a list; coerce to space-joined string
        if isinstance(v, list):
            return " ".join(str(x) for x in v)
        return v


class AppMapDbTable(DynamicBaseModel):
    table: str
    pk: str | None = None
    cols: list[str] = Field(default_factory=list)


class AppMapPayload(DynamicBaseModel):
    """Full write payload accepted by the write_app_map tool."""

    entity: str
    platform: str = "web"
    aliases: list[str] = Field(default_factory=list)
    routes: list[AppMapRoute] = Field(default_factory=list)
    actions: list[AppMapAction] = Field(default_factory=list)
    elements: list[AppMapElement] = Field(default_factory=list)
    db_tables: list[AppMapDbTable] = Field(default_factory=list)
    extra: dict = Field(default_factory=dict)
