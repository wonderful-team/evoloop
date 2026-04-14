from datetime import datetime

from pydantic import Field
from sqlmodel import Field as SQLField, SQLModel

from app.infrastructure.pydantic_base import DynamicBaseModel


class WikiPageBase(SQLModel):
    project_id: int = SQLField(index=True)
    title: str
    slug: str = SQLField(index=True)
    content: str
    parent_id: int | None = SQLField(default=None, foreign_key="wikipage.id")
    order: int = 0


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


class WikiGenerationResponse(DynamicBaseModel):
    status: str
    message: str
    task_id: str


class WikiSyncResult(DynamicBaseModel):
    project_id: int
    page_id: str
    status: str


class WikiGap(DynamicBaseModel):
    suggested_title: str | None = None
    area: str | None = None
    reason: str = ""


class WikiValidationResult(DynamicBaseModel):
    is_complete: bool = True
    gaps: list[WikiGap] = Field(default_factory=list)


class WikiPagePlan(DynamicBaseModel):
    id: str = Field(default="", description="URL-friendly slug/ID")
    title: str = "Untitled"
    description: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    importance: str = "medium"
    children: list["WikiPagePlan"] = Field(default_factory=list)


class WikiStructure(DynamicBaseModel):
    pages: list[WikiPagePlan] = Field(default_factory=list)
