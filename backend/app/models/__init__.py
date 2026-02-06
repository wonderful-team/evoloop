from sqlmodel import SQLModel

from .codebase import CodeChunk as CodeChunk, CodeEntity as CodeEntity, CodeRelation as CodeRelation, Repository as Repository, SourceFile as SourceFile
from .config import SystemConfig as SystemConfig
from .conversation import Conversation as Conversation, HumanRequest as HumanRequest, MessageReference as MessageReference, Message as Message
from .file_operation import FileOperation as FileOperation
from .learning import LearnedSkill as LearnedSkill, TraceEvent as TraceEvent
from .memory import MemoryConcept as MemoryConcept
from .persistence import (
    Checkpoint as Checkpoint,
    CheckpointBlob as CheckpointBlob,
    CheckpointMigration as CheckpointMigration,
    CheckpointWrite as CheckpointWrite,
)
from .planning import Plan as Plan, PlanStep as PlanStep
from .system import Job as Job, McpServer as McpServer, ProjectResource as ProjectResource, Tool as Tool
from .todo import TodoItem as TodoItem, TodoPriority as TodoPriority, TodoStatus as TodoStatus
from .wiki import WikiPage as WikiPage

__all__ = [
    "CodeChunk",
    "CodeEntity",
    "CodeRelation",
    "Repository",
    "SourceFile",
    "SystemConfig",
    "Conversation",
    "HumanRequest",
    "MessageReference",
    "FileOperation",
    "LearnedSkill",
    "TraceEvent",
    "MemoryConcept",
    "Checkpoint",
    "CheckpointBlob",
    "CheckpointMigration",
    "CheckpointWrite",
    "Plan",
    "PlanStep",
    "Job",
    "McpServer",
    "ProjectResource",
    "Tool",
    "TodoItem",
    "TodoPriority",
    "TodoStatus",
    "WikiPage",
    "Message",
    "GenericMessage",
    "Token",
    "TokenPayload",
    "User",
    "UserPublic",
    "UsersPublic",
]


# Generic message
class GenericMessage(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(SQLModel):
    sub: str | None = None


# User model reflecting Member Center data structure
# No longer a table=True model
class User(SQLModel):
    id: int | str  # Member Center usually uses integer member_id, but keeping str compat
    username: str | None = None
    email: str | None = None
    mobile: str | None = None
    nickname: str | None = None
    headimg: str | None = None  # Avatar URL

    # Member Center specific fields
    member_level: int = 0
    member_level_name: str | None = None
    level_expire_time: int = 0
    balance: float = 0.0
    balance_money: float = 0.0
    point: int = 0

    is_active: bool = True
    is_superuser: bool = False  # This might need special handling based on Member Center roles or config


class UserPublic(User):
    pass


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int
