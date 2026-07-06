"""Wiki database models."""
from datetime import datetime
from sqlalchemy import Column, Text
from sqlmodel import Field as SQLField
from sqlmodel import Relationship, SQLModel


class WikiPage(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    project_id: int = SQLField(index=True)
    member_id: int = SQLField(default=0, index=True, sa_column_kwargs={"comment": "Owner member ID"})
    title: str
    slug: str = SQLField(index=True)
    content: str = SQLField(sa_column=Column(Text))
    parent_id: int | None = SQLField(default=None, foreign_key="wikipage.id")
    order: int = 0
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)

    parent: "WikiPage" = Relationship(back_populates="children", sa_relationship_kwargs={"remote_side": "WikiPage.id"})
    children: list["WikiPage"] = Relationship(back_populates="parent")
