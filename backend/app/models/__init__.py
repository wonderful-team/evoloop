from sqlmodel import SQLModel

from .codebase import CodeChunk as CodeChunk
from .codebase import CodeEntity as CodeEntity
from .codebase import CodeRelation as CodeRelation
from .codebase import Repository as Repository
from .codebase import SourceFile as SourceFile
from .config import SystemConfig as SystemConfig
from .conversation import Conversation as Conversation
from .conversation import HumanRequest as HumanRequest
from .conversation import Message as Message
from .conversation import MessageReference as MessageReference
from .file_operation import FileOperation as FileOperation
from .learning import LearnedSkill as LearnedSkill
from .learning import RecordingAnnotation as RecordingAnnotation
from .learning import SynthesisJob as SynthesisJob
from .learning import TraceEvent as TraceEvent
from .memory import MemoryConcept as MemoryConcept
from .persistence import Checkpoint as Checkpoint
from .persistence import CheckpointBlob as CheckpointBlob
from .persistence import CheckpointMigration as CheckpointMigration
from .persistence import CheckpointWrite as CheckpointWrite
from .planning import Plan as Plan
from .planning import PlanStep as PlanStep
from .scheduler import AutonomousTask as AutonomousTask
from .system import Job as Job
from .system import McpServer as McpServer
from .system import ProjectResource as ProjectResource
from .system import Tool as Tool
from .todo import TodoItem as TodoItem
from .todo import TodoPriority as TodoPriority
from .todo import TodoStatus as TodoStatus
from .wiki import WikiPage as WikiPage

__all__ = [
    "CodeChunk",
    "CodeEntity",
    "AutonomousTask",
    "CodeRelation",
    "Repository",
    "SourceFile",
    "SystemConfig",
    "Conversation",
    "HumanRequest",
    "MessageReference",
    "FileOperation",
    "LearnedSkill",
    "RecordingAnnotation",
    "SynthesisJob",
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
