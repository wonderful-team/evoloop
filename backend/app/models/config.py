from sqlmodel import Field, SQLModel

class SystemConfig(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
    description: str | None = None
