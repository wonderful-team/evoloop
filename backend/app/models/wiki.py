from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy import Column, Text
from sqlmodel import Field as SQLField, Relationship, SQLModel

from app.utils.model_helpers import LegacyDictMixin


class WikiPageBase(SQLModel):
    project_id: int = SQLField(index=True)
    title: str
    slug: str = SQLField(index=True)
    content: str = SQLField(sa_column=Column(Text))  # Large text
    parent_id: int | None = SQLField(default=None, foreign_key="wikipage.id")
    order: int = 0


class WikiPage(WikiPageBase, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)

    # Self-referential relationship for hierarchy
    parent: Optional["WikiPage"] = Relationship(back_populates="children", sa_relationship_kwargs={"remote_side": "WikiPage.id"})
    children: list["WikiPage"] = Relationship(back_populates="parent")


class WikiPageCreate(WikiPageBase):
    pass


class WikiPageRead(WikiPageBase):
    id: int
    created_at: datetime
    updated_at: datetime


class WikiGenerationRequest(SQLModel):
    project_id: int
    topic: str = "Project Documentation"
    force_regenerate: bool = False


# --- Response & Structured Models ---


class WikiGenerationResponse(BaseModel, LegacyDictMixin):
    status: str
    message: str
    task_id: str


class WikiSyncResult(BaseModel, LegacyDictMixin):
    project_id: int
    page_id: str
    status: str


class WikiGap(BaseModel, LegacyDictMixin):
    suggested_title: str | None = None
    area: str | None = None
    reason: str = ""


class WikiValidationResult(BaseModel, LegacyDictMixin):
    is_complete: bool = True
    gaps: list[WikiGap] = Field(default_factory=list)


class WikiPagePlan(BaseModel, LegacyDictMixin):
    id: str = Field(default="", description="URL-friendly slug/ID")
    title: str = "Untitled"
    description: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    importance: str = "medium"
    children: list["WikiPagePlan"] = Field(default_factory=list)


class WikiStructure(BaseModel, LegacyDictMixin):
    pages: list[WikiPagePlan] = Field(default_factory=list)
