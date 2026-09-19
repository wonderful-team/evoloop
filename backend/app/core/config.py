import os
import secrets
import sys
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    Field,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


# PyInstaller support: Detect bundled environment
def _get_env_file_path():
    """Get .env file path for dev or PyInstaller environment."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, ".env")

    # Resolve relative to this file to prevent CWD dependency issues
    # This file is at: backend/app/core/config.py
    # We want: backend/../.env -> .env at project root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, "../../../.env"))


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


def expand_path(v: Any) -> str:
    if isinstance(v, str):
        return os.path.expanduser(v)
    return v


def _default_chrome_executable() -> str:
    if sys.platform == "darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif sys.platform == "win32":
        return "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    return "/usr/bin/google-chrome"


def _default_chrome_automation_data() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Google/Chrome-Automation"
        )
    elif sys.platform == "win32":
        return os.path.expanduser(
            "~\\AppData\\Local\\Google\\Chrome\\Chrome-Automation"
        )
    return os.path.expanduser("~/.config/google-chrome-automation")


def _default_device_name() -> str:
    """Default EvoLoop device name: hostname, falling back to a fixed label."""
    from app.core.device import get_hostname

    return get_hostname() or "EvoLoop-Desktop"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file=_get_env_file_path(),
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    # Execution Sandbox
    EXECUTION_MODE: Literal["local", "docker"] = "local"
    SANDBOX_IMAGE: str = "evoloop-sandbox"

    # Embedded Mode (No external dependencies)
    EMBEDDED_MODE: bool = (
        False  # True: Use SQLite + LanceDB + Huey, False: Use Postgres + Neo4j + Celery
    )

    # Guest Access Limits
    GUEST_DAILY_LIMIT: int = 10  # Max daily messages for unauthenticated guest users

    # SaaS / Multi-tenant Mode
    MULTI_TENANT_MODE: bool = False  # True: Strict token isolation, no global session cache. False: Single-user mode (safe for global cache)

    # Core App Data Directory
    EVOLOOP_APP_DATA_DIR: str = "~/.evoloop"

    # Memory System Settings
    # 记忆总开关：关闭时记忆系统整体停用（不读取、不写入、不暴露工具）。
    ENABLE_MEMORY: bool = False
    AUTO_MEMORY_EXTRACTION_INTERVAL: int = 1  # Extract every N turns (1 = every turn, 2 = every other turn, etc.)

    # Macro Sedimentation Settings (auto-creation mechanism removed, kept for future redesign)
    AUTO_MACRO_CREATION_ENABLED: bool = (
        False  # Enable automatic macro creation after successful sessions
    )

    # Skill Sedimentation Settings（§3.7）：会话含非平凡可复用解题路径时，
    # 收尾管线自动触发 skill 候选合成（pending_review，不自动激活）。
    ENABLE_SKILL_SYNTHESIS: bool = False

    # 工具级权限（对齐 OpenCode Permission ruleset）：{tool_name: "allow"|"ask"|"deny"}。
    # "ask" 时该工具调用走授权门控 → HITL 审批（approve/reject，批准后 grant 落盘）。
    # 由 engine/hooks/authorization.py 的 PRE_TOOL_USE 门控消费；空 = 全部允许。
    TOOL_PERMISSIONS: dict[str, str] = Field(default_factory=dict)

    # 工具输出截断阈值（react/truncate.py，对齐 OpenCode tool_output.max_lines/max_bytes）
    TOOL_OUTPUT_MAX_LINES: int = 2000
    TOOL_OUTPUT_MAX_BYTES: int = 32000

    # Agent 执行步数上限（react/loop.py 的 run_agent_loop 默认值）。
    # 未显式传 max_steps 时，按当前模型上下文相对 128k 基准等比缩放后，
    # 钳制在 [AGENT_MAX_STEPS_MIN, AGENT_MAX_STEPS_MAX] 区间内。
    AGENT_MAX_STEPS: int = 100
    AGENT_MAX_STEPS_MIN: int = 25
    AGENT_MAX_STEPS_MAX: int = 500
    # 单次 run 内允许的 steer（运行中注入新消息并重置步数预算）次数上限，
    # 超限后新消息回落 session 队列由下一轮 delivery 处理（防无限续期）。
    AGENT_MAX_STEERS: int = 50

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        origins = [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]
        # Add Tauri desktop app origins for embedded mode
        if self.EMBEDDED_MODE:
            origins.extend(
                [
                    "tauri://localhost",
                    "https://tauri.localhost",
                    "http://localhost",
                    "http://127.0.0.1",
                ]
            )
        return origins

    SERVICE_NAME: str = "EvoLoop"
    SENTRY_DSN: HttpUrl | None = None

    # --- Database Configuration (Postgres or SQLite) ---
    POSTGRES_SERVER: str | None = None
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    DB_ECHO: bool = False  # Added for EvoLoop compatibility
    DB_ECHO_POOL: bool = False  # Debug: log pool checkout/checkin lifecycle
    DB_CONNECT_TIMEOUT: float = 99.5  # Strategic: unified timeout for unstable networks
    DB_POOL_SIZE: int = 5  # Base connection pool size per engine
    DB_MAX_OVERFLOW: int = 10  # Max overflow connections per pool beyond pool_size

    # --- Vector Database Configuration (PostgreSQL + pgvector, separate instance) ---
    # Defaults to the same server as the main database, but with a different DB name.
    VECTOR_POSTGRES_SERVER: str | None = None
    VECTOR_POSTGRES_PORT: int = 5432
    VECTOR_POSTGRES_USER: str | None = None
    VECTOR_POSTGRES_PASSWORD: str = ""
    VECTOR_POSTGRES_DB: str | None = None

    # --- Search Backend Configuration ---
    # "auto": EMBEDDED_MODE=True → sqlite_fts, False → meilisearch
    # "sqlite_fts": Force SQLite FTS5 (local file)
    # "meilisearch": Force Meilisearch (external service)
    SEARCH_ENGINE: Literal["auto", "sqlite_fts", "meilisearch"] = "auto"
    SEARCH_DB_PATH: Annotated[str | None, BeforeValidator(expand_path)] = None

    # Meilisearch settings (used when SEARCH_ENGINE=meilisearch)
    MEILISEARCH_URL: str = "http://localhost:7700"
    MEILISEARCH_API_KEY: str = ""

    # SQLite (for embedded mode)
    # Allow override via env var for dev/prod isolation
    SQLITE_DB_PATH: Annotated[str | None, BeforeValidator(expand_path)] = None
    SQLITE_PATH: Annotated[str | None, BeforeValidator(expand_path)] = None

    # LanceDB (for embedded vector storage)
    LANCEDB_PATH: Annotated[str | None, BeforeValidator(expand_path)] = None

    # Celery Beat Schedule DB
    CELERY_SCHEDULE_DB_PATH: Annotated[str | None, BeforeValidator(expand_path)] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.EMBEDDED_MODE or not self.POSTGRES_SERVER:
            return f"sqlite+aiosqlite:///{self.SQLITE_PATH}"

        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.POSTGRES_USER or "",
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_SERVER,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    # --- EvoLoop Configuration ---
    LOG_LEVEL: str = "INFO"

    # File Upload
    # 全局模式上传目录，可通过环境变量 UPLOAD_DIR 覆盖，默认存放在应用数据目录下
    # 注意：不应放在 WORKSPACE_ROOT 下，避免被项目扫描器误识别为工程目录
    UPLOAD_DIR: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def CHAT_UPLOAD_DIR(self) -> str:
        """聊天附件统一存放目录。

        所有通过聊天输入框上传的文件（无论全局模式还是项目模式）都存放在此处，
        与项目代码目录完全隔离，不污染 WORKSPACE_ROOT。
        物理位置：~/.evoloop/uploads/（可通过环境变量 UPLOAD_DIR 覆盖）
        """
        base = self.UPLOAD_DIR or os.path.join(self.APP_DATA_DIR, "uploads")
        os.makedirs(base, exist_ok=True)
        return base

    # Graph (Neo4j) - Only used when EMBEDDED_MODE=false
    NEO4J_URI: str | None = "bolt://localhost:7687"
    NEO4J_USER: str | None = "neo4j"
    NEO4J_PASSWORD: str | None = None

    # Cache backend (Redis in production, FileCache in embedded mode)
    REDIS_URL: str | None = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = Field(120, validation_alias="REDIS_MAX_CONNECTIONS")

    # AI Models Storage Configuration
    MODELS_DIR: Annotated[str | None, BeforeValidator(expand_path)] = None  # Directory for storing AI models (embeddings, etc.)

    # HuggingFace endpoint / mirror. Used by huggingface_hub and the bundled model
    # download helpers (e.g. bge-base-zh-v1.5 GGUF). Defaults to hf-mirror.com for
    # better accessibility in mainland China; override via HF_ENDPOINT env var.
    HF_ENDPOINT: str = Field("https://hf-mirror.com", validation_alias="HF_ENDPOINT")

    # Embedding Configuration
    EMBEDDING_DIMENSIONS: int = 768  # Nomic / Local Default
    # Lightning Channel default GGUF directory
    LIGHTNING_GGUF_DIR: str = Field(default="")

    # Search Optimization
    ENABLE_QUERY_REWRITING: bool = True  # P1: Cross-Lingual Query Rewriting

    ENABLE_VISION_OCR: bool = True
    ENABLE_MACRO_SELF_HEALING: bool = False
    ENABLE_WIKI_TOOLS: bool = False
    ROUTE_INDEX_REQUIRE_VERIFIED: bool = True

    # 是否启用代码库文件监听器（watchdog）。关闭后不再实时监听项目目录变更，
    # 可显著减少 macOS FSEvents 噪声和 CPU 占用；增量索引需改由手动触发 full index。
    ENABLE_CODEBASE_FILE_WATCHER: bool = True

    # 是否启用本地环境控制工具（浏览器、桌面、手机）。可以根据实际需要开启或关闭。
    # 纯服务端部署推荐关闭 (False)，需要 AI 控制真实设备时开启 (True)。
    ENABLE_ENVIRONMENT_CONTROLS: bool = False

    # Screenshot Configuration
    ENABLE_PARTIAL_SCREENSHOT: bool = True  # True: Auto-capture current window region, False: Full screen only

    # --- Learning / Skill Synthesis Configuration ---
    # Maximum keyframes to extract for skill synthesis (multimodal learning)
    # Higher values = more context for LLM but higher token cost
    MAX_KEYFRAMES: int = 50

    # Path Security
    # 额外允许的路径前缀（默认关闭，避免 Agent 把文件写到 /tmp 等系统临时目录）。
    # Agent 的写入/命令沙箱只允许当前项目工作目录；需要额外白名单时在此追加。
    ALLOWED_PATH_PREFIXES: list[str] = []

    # --- Multi-tenant MCP access control (multi-tenant isolation) ---
    # Allows member identities to call MCP servers in multi-tenant mode; servers outside this list
    # (e.g. local-postgres / member-center-ops) are operations-managed, can read other members' data, and are only open to admin.
    OPS_ENABLED_MCP_SERVERS: list[str] = []

    # --- Cognitive Brain Configuration ---
    # Memory Architecture Toggle (Phase 4 Autonomy)

    # File System
    # Brain Memory now stored in ~/.evoloop/memory/ for consistency with other app data
    @computed_field
    @property
    def BRAIN_MEMORY_ROOT(self) -> str:
        """Brain memory storage location in app data directory."""
        path = os.path.join(self.APP_DATA_DIR, "memory")
        os.makedirs(path, exist_ok=True)
        return path

    # Skills Directory
    @computed_field
    @property
    def SKILLS_DIR(self) -> str:
        """Skills storage directory in app data directory."""
        path = os.path.join(self.APP_DATA_DIR, "skills")
        os.makedirs(path, exist_ok=True)
        return path

    # Browser Control (Native CDP)
    CHROME_CDP_URL: str = Field(
        "http://localhost:9222",
        validation_alias="EVOLOOP_CHROME_CDP_URL"
    )
    CHROME_EXECUTABLE: str = Field(
        default_factory=_default_chrome_executable,
        validation_alias="EVOLOOP_CHROME_EXECUTABLE",
    )
    CHROME_AUTOMATION_USER_DATA: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=_default_chrome_automation_data,
        validation_alias="EVOLOOP_CHROME_AUTOMATION_USER_DATA",
    )
    CHROME_STARTUP_TIMEOUT: int = Field(
        5, validation_alias="EVOLOOP_CHROME_STARTUP_TIMEOUT"
    )

    # EvoCloud API
    EVOCLOUD_API_URL: str = Field(
        "http://127.0.0.1", validation_alias="EVOCLOUD_API_URL"
    )
    EVOCLOUD_WS_URL: str = Field(
        "ws://127.0.0.1/ws", validation_alias="EVOCLOUD_WS_URL"
    )
    EVOCLOUD_API_KEY: str | None = Field(None, validation_alias="EVOCLOUD_API_KEY")
    EVOCLOUD_API_SECRET: str | None = Field(
        None, validation_alias="EVOCLOUD_API_SECRET"
    )
    # SSO：Member Center S2S 桥接密钥（后台免登链路）
    EVOCLOUD_SSO_KEY: str | None = Field(
        None, validation_alias="EVOCLOUD_SSO_KEY"
    )
    # SSO：Member Center 直连地址（仅 /api/sso/* 的 redeem 使用）。
    # 线上缺省 None → 沿用 EVOCLOUD_API_URL + /member（nginx 反代）；
    # 本地开发矩阵不在云域下，SSO 兑换需直指矩阵地址。
    # 注意：login/refreshToken/user_info 等其余 member API 的用户体系在云，
    # 恒走 EVOCLOUD_API_URL —— 此前整条 member 通道直指矩阵曾污染 identity
    # store（LLM/device claim 401），勿再扩大该覆盖范围。
    EVOCLOUD_MEMBER_URL: str | None = Field(
        None, validation_alias="EVOCLOUD_MEMBER_URL"
    )


    # Client / Device Info
    EVOCLOUD_ACCESS_TOKEN: str | None = Field(
        None, validation_alias="EVOCLOUD_ACCESS_TOKEN"
    )
    EVOCLOUD_DEVICE_NAME: str | None = Field(
        default_factory=_default_device_name, validation_alias="EVOCLOUD_DEVICE_NAME"
    )
    EVOCLOUD_DEVICE_TYPE: str = Field(
        "desktop", validation_alias="EVOCLOUD_DEVICE_TYPE"
    )
    EVOCLOUD_DEVICE_DESCRIPTION: str = Field(
        "", validation_alias="EVOCLOUD_DEVICE_DESCRIPTION"
    )
    EVOCLOUD_SSL_VERIFY: bool = Field(True, validation_alias="EVOCLOUD_SSL_VERIFY")

    # Mobile Sync
    # 是否启用与移动端的数据同步通道。
    # 设置为 False 可完全屏蔽以下所有对外通信：
    #   - WebSocket 连接到 Gateway（含 handshake / ping / message_sync /
    #     agent_run_completed / command_ack / query_response）
    #   - 对话历史 HTTP 同步（全量 + 增量）
    #   - 设备注册与 Mobile 客户端绑定
    # 适用场景：纯服务器部署，不需要移动端接入时（MOBILE_SYNC_ENABLED=false）。
    MOBILE_SYNC_ENABLED: bool = Field(True, validation_alias="MOBILE_SYNC_ENABLED")

    # --- Deprecated Configuration (Phase 4 Cleanup) ---
    USE_CLIENT_FOR_TOOLS: bool = False  # @deprecated: Will be replaced by dynamic transport selection
    CLOUD_ONLY_MODE: bool = False  # @deprecated: Will be replaced by hybrid execution mode
    CLIENT_CALLBACK_URL: str | None = None  # @deprecated: Managed by WebSocket handshake
    CLIENT_TOOL_TIMEOUT: float = 300.0  # Default timeout for client tool execution

    # Project Management
    # 启用/禁用项目自动发现（默认禁用）—— 已迁移到 SystemConfigService (DB)，不再通过 .env 配置

    # Artifacts (Relative to ~/.evoloop in home dir for persistence, or subfolder of WORKSPACE_ROOT?)
    # Decision: Keep them in user app data dir to avoid cluttering projects root or ephemeral CWD.
    @computed_field
    @property
    def APP_DATA_DIR(self) -> str:
        """Centralized application data directory."""
        return expand_path(self.EVOLOOP_APP_DATA_DIR)

    @computed_field
    @property
    def BROWSER_ARTIFACTS_DIR(self) -> str:
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "browser")
        os.makedirs(path, exist_ok=True)
        return path

    @computed_field
    @property
    def SCREENSHOTS_DIR(self) -> str:
        """Legacy screenshots directory - kept for backward compatibility."""
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "screenshots")
        os.makedirs(path, exist_ok=True)
        return path

    # --- Hierarchical Screenshot Storage (分层截图存储) ---

    @computed_field
    @property
    def SCREENSHOTS_TEMP_DIR(self) -> str:
        """Temporary screenshots - for immediate OCR/processing, auto-cleaned."""
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "screenshots", "temp")
        os.makedirs(path, exist_ok=True)
        return path

    @computed_field
    @property
    def SCREENSHOTS_ATLAS_DIR(self) -> str:
        """Atlas learning screenshots - stored by app for knowledge graph building."""
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "screenshots", "atlas")
        os.makedirs(path, exist_ok=True)
        return path

    @computed_field
    @property
    def SCREENSHOTS_DEBUG_DIR(self) -> str:
        """Debug screenshots - for troubleshooting and error analysis."""
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "screenshots", "debug")
        os.makedirs(path, exist_ok=True)
        return path

    @computed_field
    @property
    def SCREENSHOTS_DATASET_DIR(self) -> str:
        """Dataset screenshots - for IL training data collection."""
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "screenshots", "dataset")
        os.makedirs(path, exist_ok=True)
        return path

    # Screenshot retention policy (in days)
    SCREENSHOT_TEMP_RETENTION_DAYS: int = 1
    SCREENSHOT_DEBUG_RETENTION_DAYS: int = 7
    SCREENSHOT_ATLAS_RETENTION_DAYS: int = 90  # Longer retention for knowledge graph
    SCREENSHOT_DATASET_RETENTION_DAYS: int = 365  # Keep training data for a year

    # --- Screen Recording Storage (屏幕录制存储) ---

    @computed_field
    @property
    def SCREEN_RECORDINGS_DIR(self) -> str:
        """Screen recording videos - for IL training and replay."""
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "recordings")
        os.makedirs(path, exist_ok=True)
        return path

    @computed_field
    @property
    def ANDROID_RECORDINGS_DIR(self) -> str:
        """Android screen recordings directory."""
        path = os.path.join(self.SCREEN_RECORDINGS_DIR, "android")
        os.makedirs(path, exist_ok=True)
        return path

    @computed_field
    @property
    def SCREEN_RECORDING_FRAMES_DIR(self) -> str:
        """Extracted frames from screen recordings."""
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "recordings", "frames")
        os.makedirs(path, exist_ok=True)
        return path

    # Screen recording retention policy
    SCREEN_RECORDING_RETENTION_DAYS: int = 30  # 保留30天
    SCREEN_RECORDING_MAX_SIZE_GB: int = 10  # 总容量限制10GB
    SCREEN_RECORDING_MAX_DURATION_MIN: int = 10  # 单次录制最大10分钟
    SCREEN_RECORDING_MAX_SIZE_MB: int = 500  # 单次录制最大500MB

    @model_validator(mode="after")
    def _set_default_paths(self) -> Self:
        """Set default paths based on EVOLOOP_APP_DATA_DIR."""
        base_dir = expand_path(self.EVOLOOP_APP_DATA_DIR)

        if not self.SEARCH_DB_PATH:
            self.SEARCH_DB_PATH = os.path.join(base_dir, "database/search.db")

        if not self.SQLITE_PATH:
            self.SQLITE_PATH = self.SQLITE_DB_PATH or os.path.join(
                base_dir, "database/backend.db"
            )

        if not self.LANCEDB_PATH:
            self.LANCEDB_PATH = os.path.join(base_dir, "database/lancedb")

        if not self.CELERY_SCHEDULE_DB_PATH:
            self.CELERY_SCHEDULE_DB_PATH = os.path.join(
                base_dir, "database/celerybeat-schedule.db"
            )

        if not self.MODELS_DIR:
            self.MODELS_DIR = os.path.join(base_dir, "models")

        return self

    @model_validator(mode="after")
    def _setup_external_env(self) -> Self:
        """Set environment variables for external libraries (ModelScope, HuggingFace)."""
        if self.MODELS_DIR:
            os.environ["MODELSCOPE_CACHE"] = self.MODELS_DIR
            os.environ["HF_HOME"] = os.path.join(
                self.MODELS_DIR, ".cache", "huggingface"
            )
            gguf_dir = os.path.join(self.MODELS_DIR, "gguf")
            os.makedirs(gguf_dir, exist_ok=True)
            os.environ["LIGHTNING_GGUF_DIR"] = gguf_dir
        # Ensure huggingface_hub and other download helpers use the configured mirror.
        os.environ["HF_ENDPOINT"] = self.HF_ENDPOINT.rstrip("/")
        return self

    # Logic Limits
    MEMORY_SEARCH_LIMIT: int = 10
    TREE_VIEW_MAX_LINES: int = 1500

    # Memory
    SESSION_IDLE_TIMEOUT: int = 1800  # 语音会话空闲超时（秒），超时自动关闭
    MIN_MESSAGES_FOR_EXTRACTION: int = 4
    MAX_EXTRACTION_TURNS: int = 5
    MAX_MEMORY_SELECTIONS: int = 5
    MEMORY_MIN_RELEVANCE: float = 0.7
    MEMORY_QUALITY_CHECK: bool = True
    MEMORY_AUTO_CLEANUP: bool = False
    HOT_MEMORY_MAX_CHARS: int = 8000
    COLD_MEMORY_RESULTS: int = 5
    MEMORY_PRUNE_THRESHOLD: int = 100
    CONTEXT_WINDOW_SIZE: int = 20
    MEMORY_MAINTENANCE_ENABLED: bool = False

    # Subagent（并行执行）：进程重启后 stale running/awaiting 收割阈值（秒）
    SUBAGENT_STALE_AFTER_SECONDS: int = 3600

    @computed_field  # type: ignore[prop-decorator]
    @property
    def VECTOR_DATABASE_URI(self) -> str | None:
        """URI for the dedicated vector database (pgvector). None in embedded mode."""
        if self.EMBEDDED_MODE:
            return None
        server = self.VECTOR_POSTGRES_SERVER or self.POSTGRES_SERVER
        if not server:
            return None
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.VECTOR_POSTGRES_USER or self.POSTGRES_USER or "",
                password=self.VECTOR_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD,
                host=server,
                port=self.VECTOR_POSTGRES_PORT or self.POSTGRES_PORT,
                path=self.VECTOR_POSTGRES_DB or self.POSTGRES_DB,
            )
        )

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        # Only check Postgres password in non-embedded mode
        if not self.EMBEDDED_MODE and self.POSTGRES_PASSWORD:
            self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)

        return self

    @model_validator(mode="after")
    def _configure_embedded_mode(self) -> Self:
        """Auto-disable external services when EMBEDDED_MODE is enabled."""
        if self.EMBEDDED_MODE:
            self.NEO4J_URI = None
            self.NEO4J_USER = None
            self.NEO4J_PASSWORD = None
            self.REDIS_URL = None
            if self.SEARCH_ENGINE != "meilisearch":
                self.MEILISEARCH_URL = None
                self.MEILISEARCH_API_KEY = None
        return self

    @model_validator(mode="after")
    def _configure_allowed_paths(self) -> Self:
        """将应用数据目录（~/.evoloop）动态注入安全访问白名单。

        确保 Agent 工具链在全局模式下可以访问 ~/.evoloop/uploads 中的上传文件，
        而不触发路径越界安全校验。
        """
        app_data = os.path.expanduser(self.APP_DATA_DIR)
        current_prefixes = list(self.ALLOWED_PATH_PREFIXES)
        if app_data not in current_prefixes:
            current_prefixes.append(app_data)
            self.ALLOWED_PATH_PREFIXES = current_prefixes
        return self


settings = Settings()  # type: ignore
