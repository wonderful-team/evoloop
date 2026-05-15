import os
import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    Field,
    HttpUrl,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


# PyInstaller support: Detect bundled environment
def _get_env_file_path():
    """Get .env file path for dev or PyInstaller environment."""
    import sys
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, '.env')
    return '../.env'


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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file=_get_env_file_path(),
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    # Execution Sandbox
    EXECUTION_MODE: Literal["local", "docker"] = "local"
    SANDBOX_IMAGE: str = "evoloop-sandbox"

    # Embedded Mode (No external dependencies)
    EMBEDDED_MODE: bool = False  # True: Use SQLite + LanceDB + LocalCelery, False: Use Postgres + Neo4j + Redis

    # Memory System Settings
    AUTO_MEMORY_EXTRACTION: bool = True  # Enable automatic memory extraction at conversation end
    AUTO_MEMORY_EXTRACTION_INTERVAL: int = 1  # Extract every N turns (1 = every turn, 2 = every other turn, etc.)

    BACKEND_CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        origins = [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [self.FRONTEND_HOST]
        # Add Tauri desktop app origins for embedded mode
        if self.EMBEDDED_MODE:
            origins.extend([
                "tauri://localhost",
                "https://tauri.localhost",
                "http://localhost",
                "http://127.0.0.1",
            ])
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
    DB_CONNECT_TIMEOUT: float = 99.5  # Strategic: unified timeout for unstable networks

    # --- Vector Database Configuration (PostgreSQL + pgvector, separate instance) ---
    # Defaults to the same server as the main database, but with a different DB name.
    VECTOR_POSTGRES_SERVER: str | None = None
    VECTOR_POSTGRES_PORT: int = 5432
    VECTOR_POSTGRES_USER: str | None = None
    VECTOR_POSTGRES_PASSWORD: str = ""
    VECTOR_POSTGRES_DB: str = "evoloop_vector"

    # --- Search Backend Configuration ---
    # "auto": EMBEDDED_MODE=True → sqlite_fts, False → meilisearch
    # "sqlite_fts": Force SQLite FTS5 (local file)
    # "meilisearch": Force Meilisearch (external service)
    SEARCH_ENGINE: Literal["auto", "sqlite_fts", "meilisearch"] = "auto"
    SEARCH_DB_PATH: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/.evoloop/knowledge/search.db")
    )
    # Meilisearch settings (used when SEARCH_ENGINE=meilisearch)
    MEILISEARCH_URL: str = "http://localhost:7700"
    MEILISEARCH_API_KEY: str = ""

    # SQLite (for embedded mode)
    # Allow override via env var for dev/prod isolation
    SQLITE_PATH: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser(
            os.getenv("SQLITE_DB_PATH", "~/.evoloop/backend.db")
        ),
    )

    # LanceDB (for embedded vector storage)
    LANCEDB_PATH: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/.evoloop/lancedb"),
    )

    # Knowledge Base Storage
    KNOWLEDGE_BASE_PATH: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/.evoloop/knowledge"),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.EMBEDDED_MODE or not self.POSTGRES_SERVER:
            return f"sqlite+aiosqlite:///{self.SQLITE_PATH}"

        return str(PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER or "",
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        ))

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.SERVICE_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

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

    # Graph (Neo4j) - Optional, disabled in embedded mode
    NEO4J_URI: str | None = "bolt://localhost:7687"
    NEO4J_USER: str | None = "neo4j"
    NEO4J_PASSWORD: str | None = None
    USE_NEO4J: bool = True  # Set to False to disable Neo4j

    # Cache backend (Redis in production, FileCache in embedded mode)
    REDIS_URL: str | None = "redis://localhost:6379/0"

    # Task Queue Backend (celery | huey | local | auto)
    # - celery: Full Celery with Redis (requires Redis, not available in embedded mode)
    # - huey: Huey with SQLite (recommended for embedded mode, no external deps)
    # - local: In-memory LocalCelery (deprecated, tasks lost on restart)
    # - auto: Auto-detect based on EMBEDDED_MODE (huey for embedded, celery otherwise)
    TASK_QUEUE_BACKEND: Literal["celery", "huey", "local", "auto"] = "auto"

    # Voice/TTS Configuration
    TTS_PROVIDER: str = "auto"  # auto | system-tts | edge-tts
    TTS_DEFAULT_VOICE: str = "zh-CN-Tingting"  # macOS 系统语音: 婷婷
    TTS_DEFAULT_SPEED: float = 1.0  # 0.5 - 2.0

    # Voice/STT Configuration (FunASR - local, Chinese optimized)
    FUNASR_MODEL: str = "paraformer-zh"  # paraformer-zh | paraformer-zh-plus | paraformer-zh-streaming
    FUNASR_DEVICE: str = "cpu"  # cpu | cuda

    # AI Models Storage Configuration
    MODELS_DIR: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/.evoloop/models"),
    )  # Directory for storing AI models (FunASR, embeddings, etc.)

    # Embedding Configuration
    EMBEDDING_DIMENSIONS: int = 768  # Nomic / Local Default
    HF_ENDPOINT: str = "https://huggingface.co"

    # Wiki Generation
    WIKI_EXTRACT_CONCEPTS: bool = True  # Extract and store concepts from Wiki pages to Agent memory

    # Search Optimization
    ENABLE_QUERY_REWRITING: bool = True  # P1: Cross-Lingual Query Rewriting

    ENABLE_VISION_OCR: bool = True
    ENABLE_MACRO_SELF_HEALING: bool = True

    # Screenshot Configuration
    ENABLE_PARTIAL_SCREENSHOT: bool = True  # True: Auto-capture current window region, False: Full screen only

    # --- Learning / Skill Synthesis Configuration ---
    # Maximum keyframes to extract for skill synthesis (multimodal learning)
    # Higher values = more context for LLM but higher token cost
    MAX_KEYFRAMES: int = 50

    GOOGLE_API_KEY: str | None = None
    BRAVE_API_KEY: str | None = None

    # Path Security
    ALLOWED_PATH_PREFIXES: list[str] = [
        "/tmp/dataset",
        "/tmp/evoloop"
    ]

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

    REFLECTIVE_DRIVER_TYPE: str = "active"

    # Browser Control (Native CDP)
    CHROME_CDP_URL: str = Field("http://localhost:9222", validation_alias="EVOLOOP_CHROME_CDP_URL")
    CHROME_EXECUTABLE: str = Field(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        validation_alias="EVOLOOP_CHROME_EXECUTABLE",
    )
    CHROME_USER_DATA: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/Library/Application Support/Google/Chrome"),
        validation_alias="EVOLOOP_CHROME_USER_DATA",
    )
    CHROME_AUTOMATION_USER_DATA: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/Library/Application Support/Google/Chrome-Automation"),
        validation_alias="EVOLOOP_CHROME_AUTOMATION_USER_DATA",
    )
    CHROME_PROFILE: str = Field("Default", validation_alias="EVOLOOP_CHROME_PROFILE")
    CHROME_STARTUP_TIMEOUT: int = Field(5, validation_alias="EVOLOOP_CHROME_STARTUP_TIMEOUT")

    # EvoCloud API
    EVOCLOUD_API_URL: str = Field("http://127.0.0.1", validation_alias="EVOCLOUD_API_URL")
    EVOCLOUD_WS_URL: str = Field("ws://127.0.0.1/ws", validation_alias="EVOCLOUD_WS_URL")
    EVOCLOUD_API_KEY: str | None = Field(None, validation_alias="EVOCLOUD_API_KEY")
    EVOCLOUD_API_SECRET: str | None = Field(None, validation_alias="EVOCLOUD_API_SECRET")

    # Client / Device Info
    EVOCLOUD_ACCESS_TOKEN: str | None = Field(None, validation_alias="EVOCLOUD_ACCESS_TOKEN")
    EVOCLOUD_DEVICE_NAME: str | None = Field("EvoLoop-Desktop", validation_alias="EVOCLOUD_DEVICE_NAME")
    EVOCLOUD_SSL_VERIFY: bool = Field(True, validation_alias="EVOCLOUD_SSL_VERIFY")

    @field_validator("EVOCLOUD_SSL_VERIFY", mode="before")
    @classmethod
    def parse_ssl_verify(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    # --- Deprecated Configuration (Phase 4 Cleanup) ---
    USE_CLIENT_FOR_TOOLS: bool = False  # @deprecated: Will be replaced by dynamic transport selection
    CLOUD_ONLY_MODE: bool = False       # @deprecated: Will be replaced by hybrid execution mode
    CLIENT_CALLBACK_URL: str | None = None  # @deprecated: Managed by WebSocket handshake

    # Project Management
    # 启用/禁用项目自动发现（默认禁用）—— 已迁移到 SystemConfigService (DB)，不再通过 .env 配置

    # Artifacts (Relative to ~/.evoloop in home dir for persistence, or subfolder of WORKSPACE_ROOT?)
    # Decision: Keep them in user app data dir to avoid cluttering projects root or ephemeral CWD.
    @computed_field
    @property
    def APP_DATA_DIR(self) -> str:
        """Centralized application data directory."""
        return os.getenv("EVOLOOP_APP_DATA_DIR", os.path.join(os.path.expanduser("~"), ".evoloop"))

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
    SCREEN_RECORDING_MAX_SIZE_GB: int = 10     # 总容量限制10GB
    SCREEN_RECORDING_MAX_DURATION_MIN: int = 10  # 单次录制最大10分钟
    SCREEN_RECORDING_MAX_SIZE_MB: int = 500    # 单次录制最大500MB

    @model_validator(mode="after")
    def _setup_external_env(self) -> Self:
        """Set environment variables for external libraries (ModelScope, HuggingFace)."""
        os.environ["MODELSCOPE_CACHE"] = self.MODELS_DIR
        os.environ["HF_ENDPOINT"] = self.HF_ENDPOINT
        return self

    # Logic Limits
    MEMORY_SEARCH_LIMIT: int = 5
    RESEARCH_MAX_ITERATIONS: int = 5
    TREE_VIEW_MAX_LINES: int = 1500
    RECURSION_LIMIT: int = 100  # Default LangGraph recursion limit

    # --- RAG & Search Tunable Parameters ---
    DEFAULT_SEARCH_TOP_K: int = 10
    MAX_SEARCH_DEPTH: int = 3
    MIN_RELEVANCE_SCORE: float = 0.6

    # Chunking
    DEFAULT_CHUNK_SIZE: int = 1000
    MAX_CHUNK_SIZE: int = 4000
    DEFAULT_CHUNK_OVERLAP: int = 200

    # Memory
    MAX_SESSION_HISTORY: int = 20
    MEMORY_RELEVANCE_THRESHOLD: float = 0.75
    MAX_MEMORY_ITEMS: int = 1000

    # Dynamic Agents
    SUPERVISOR_AGENT_MAX_STEPS: int = 20
    WORKER_AGENT_MAX_STEPS: int = 50
    FINISH_AGENT_MAX_STEPS: int = 10

    # Long-horizon task limits (e.g. wiki generation, large codebase analysis)
    LONG_HORIZON_SUPERVISOR_MAX_STEPS: int = 100
    LONG_HORIZON_RECURSION_LIMIT: int = 250

    # --- Protocol Dynamic Loading (Phase 1 Optimization) ---
    # Feature flag for dynamic protocol loading - reduces Worker System Prompt size
    DYNAMIC_PROTOCOL_LOADING: bool = Field(
        default=False,
        validation_alias="DYNAMIC_PROTOCOL_LOADING"
    )  # Set to True to enable dynamic protocol injection based on user intent

    # Protocol matcher confidence threshold (0.0 - 1.0)
    # Higher = more conservative, only inject protocols when strongly matched
    PROTOCOL_MATCHER_THRESHOLD: float = Field(
        default=0.7,
        validation_alias="PROTOCOL_MATCHER_THRESHOLD"
    )

    # Protocol loader cache TTL in seconds
    PROTOCOL_LOADER_CACHE_TTL: int = Field(
        default=300,  # 5 minutes
        validation_alias="PROTOCOL_LOADER_CACHE_TTL"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def VECTOR_DATABASE_URI(self) -> str | None:
        """URI for the dedicated vector database (pgvector). None in embedded mode."""
        if self.EMBEDDED_MODE:
            return None
        server = self.VECTOR_POSTGRES_SERVER or self.POSTGRES_SERVER
        if not server:
            return None
        return str(PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.VECTOR_POSTGRES_USER or self.POSTGRES_USER or "",
            password=self.VECTOR_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD,
            host=server,
            port=self.VECTOR_POSTGRES_PORT or self.POSTGRES_PORT,
            path=self.VECTOR_POSTGRES_DB,
        ))

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
            self.USE_NEO4J = False
            self.NEO4J_URI = None
            self.REDIS_URL = None
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
