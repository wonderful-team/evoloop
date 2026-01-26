from datetime import datetime
from typing import Optional, List
from sqlalchemy import Text, Column
from sqlmodel import SQLModel, Field, Relationship


class WikiPageBase(SQLModel):
    project_id: int = Field(index=True)
    title: str
    slug: str = Field(index=True)
    content: str = Field(sa_column=Column(Text))  # Large text
    parent_id: Optional[int] = Field(default=None, foreign_key="wikipage.id")
    order: int = 0


class WikiPage(WikiPageBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Self-referential relationship for hierarchy
    parent: Optional["WikiPage"] = Relationship(back_populates="children", sa_relationship_kwargs={"remote_side": "WikiPage.id"})
    children: List["WikiPage"] = Relationship(back_populates="parent")


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
