from datetime import datetime

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
