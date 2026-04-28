from sqlmodel import SQLModel

from .checkpoint import Checkpoint as Checkpoint
from .checkpoint import CheckpointBlob as CheckpointBlob
from .checkpoint import CheckpointMigration as CheckpointMigration
from .checkpoint import CheckpointWrite as CheckpointWrite
from .citation import CitationEvent as CitationEvent
from .citation import DocStat as DocStat
from .citation import SessionDoc as SessionDoc
from .codebase import CodeChunk as CodeChunk
from .codebase import CodeEntity as CodeEntity
from .codebase import CodeRelation as CodeRelation
from .codebase import Repository as Repository
from .codebase import SourceFile as SourceFile
from .conversation import AgentActivity as AgentActivity
from .conversation import Conversation as Conversation
from .conversation import HumanRequest as HumanRequest
from .conversation import Message as Message
from .conversation import MessageReference as MessageReference
from .conversation import ThreadSequence as ThreadSequence
from .file_operation import FileOperation as FileOperation
from .learning import LearnedSkill as LearnedSkill
from .learning import SynthesisJob as SynthesisJob
from .learning import TraceEvent as TraceEvent
from .maintenance import MaintenanceReport as MaintenanceReport
from .memory import MemoryConcept as MemoryConcept
from .planning import Plan as Plan
from .planning import PlanStep as PlanStep
from .scheduler import AutonomousTask as AutonomousTask
from .schemas.auth import CacheInvalidateResponse as CacheInvalidateResponse
from .schemas.auth import EvoCloudProxyResponse as EvoCloudProxyResponse
from .schemas.auth import LoginResult as LoginResult
from .schemas.auth import MemberBenefitsResponse as MemberBenefitsResponse
from .system import Job as Job
from .system import McpServer as McpServer
from .system import ProjectResource as ProjectResource
from .system import SystemConfig as SystemConfig
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
    "EvoCloudProxyResponse",
    "LoginResult",
    "MemberBenefitsResponse",
    "CacheInvalidateResponse",
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


# User model reflecting Member Center /api/member/info response structure
# No longer a table=True model - data is fetched from Member Center
class User(SQLModel):
    # Core identification
    id: int | str  # member_id from Member Center
    username: str | None = None
    nickname: str | None = None
    mobile: str | None = None
    email: str | None = None
    headimg: str | None = None  # Avatar URL

    # Member level info
    member_level: int = 0
    member_level_name: str | None = None
    member_level_type: int = 0
    level_expire_time: int = 0

    # Member labels
    member_label: int = 0
    member_label_name: str | None = None
    member_code: str | None = None

    # Account assets
    point: int = 0  # 积分
    balance: float = 0.0  # 余额
    balance_money: float = 0.0  # 可提现余额
    growth: int = 0  # 成长值

    # Status flags
    status: int = 1  # 0=disabled, 1=active (mapped from Member Center)
    has_password: bool = False  # password field from MC (0/1 -> bool)
    is_edit_username: int = 0  # Whether username has been edited
    is_fenxiao: int = 0  # Whether user is a distributor

    # Profile info
    realname: str | None = None  # Real name
    sex: int = 0  # 0=unknown, 1=male, 2=female
    birthday: str | None = None  # Birthday

    # Referral info
    source_member: int = 0  # Referrer member ID

    # Address info
    province_id: int = 0
    city_id: int = 0
    district_id: int = 0
    address: str | None = None
    full_address: str | None = None
    longitude: float = 0.0
    latitude: float = 0.0

    # Third-party login (optional, if needed)
    wx_openid: str | None = None
    wx_unionid: str | None = None

    # Compatibility fields
    is_active: bool = True  # Derived from status == 1
    is_superuser: bool = False  # Reserved for admin roles


class UserPublic(User):
    pass


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int
