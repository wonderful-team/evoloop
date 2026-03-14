import os
import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    BeforeValidator,
    EmailStr,
    Field,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def expand_path(v: Any) -> str:
    if isinstance(v, str):
        return os.path.expanduser(v)
    return v


class Settings(BaseSettings):
    """EvoLoop Client Configuration

    Client-only settings (PostgreSQL/Neo4j/Redis removed - server branch only).
    """
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # --- Core Settings ---
    PROJECT_NAME: str = "EvoLoop Client"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    LOG_LEVEL: str = "INFO"

    # --- SQLite (Client-only Database) ---
    DB_ECHO: bool = False
    SQLITE_PATH: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/.evoloop/data.db"),
    )

    @computed_field
    @property
    def DATABASE_URI(self) -> str:
        """SQLite database URI (client-only)."""
        return f"sqlite+aiosqlite:///{self.SQLITE_PATH}"

    # LanceDB (Client Vector Storage)
    LANCEDB_PATH: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/.evoloop/lancedb"),
    )

    # --- Agent Engine ---
    # "simple": Lightweight ReAct loop (client mode)
    AGENT_ENGINE_MODE: Literal["simple", "full"] = "simple"

    # LanceDB (Vector Storage)
    LANCEDB_PATH: Annotated[str, BeforeValidator(expand_path)] = Field(
        default_factory=lambda: os.path.expanduser("~/.evoloop/lancedb"),
    )

    # Cloud Connection
    EVOLOOP_CLOUD_URL: str = "https://api.evoloop.ai"
    DEVICE_ID: str | None = None  # Unique device identifier

    # Server Connection (for AI proxy)
    SERVER_URL: str = "http://localhost:8000"  # Local Server URL for LLM/Vision/Embedding proxy
    SERVER_API_KEY: str | None = None  # Optional API key for Server authentication

    # LLM Providers (default to Server proxy)
    OPENAI_API_KEY: str = "sk-client-proxy"  # Dummy key, actual key is on Server
    OPENAI_BASE_URL: str = "http://localhost:8000/api/v1/proxy"  # Server proxy endpoint
    OPENAI_MODEL_NAME: str = "gpt-4o"

    # Embedding Configuration (default to Server proxy)
    EMBEDDING_PROVIDER: Literal["openai", "ollama", "dashscope", "huggingface", "local"] = "openai"
    EMBEDDING_BASE_URL: str = "http://localhost:8000/api/v1/proxy"  # Server proxy endpoint
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 768

    # Wiki Generation
    WIKI_EXTRACT_CONCEPTS: bool = True  # Extract and store concepts from Wiki pages to Agent memory

    # Search Optimization
    ENABLE_QUERY_REWRITING: bool = True  # P1: Cross-Lingual Query Rewriting

    ENABLE_VISION_OCR: bool = True
    ENABLE_MACRO_SELF_HEALING: bool = True

    # --- Learning / Skill Synthesis Configuration ---
    # Maximum keyframes to extract for skill synthesis (multimodal learning)
    # Higher values = more context for LLM but higher token cost
    MAX_KEYFRAMES: int = 50

    ANTHROPIC_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None
    BRAVE_API_KEY: str | None = None

    # --- Cognitive Configuration ---
    # Memory now uses cloud API (server-side Neo4j removed from client branch)

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

    # Drivers: 'mock', 'local_ssm', 'remote_api'
    SSM_MODEL_NAME: str = "local-model"  # Default for LM Studio/Ollama
    SSM_API_BASE: str = "http://localhost:1234/v1"  # For LM Studio / LocalAI

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
    EVOCLOUD_API_URL: str = Field("https://mall.imagicbox.cn", validation_alias="EVOCLOUD_API_URL")
    EVOCLOUD_WS_URL: str = Field("wss://mall.imagicbox.cn/wss/", validation_alias="EVOCLOUD_WS_URL")
    EVOCLOUD_API_KEY: str | None = Field(None, validation_alias="EVOCLOUD_API_KEY")
    EVOCLOUD_API_SECRET: str | None = Field(None, validation_alias="EVOCLOUD_API_SECRET")

    # Client / Device Info
    EVOCLOUD_ACCESS_TOKEN: str | None = Field(None, validation_alias="EVOCLOUD_ACCESS_TOKEN")
    EVOCLOUD_DEVICE_NAME: str | None = Field("EvoLoop-Desktop", validation_alias="EVOCLOUD_DEVICE_NAME")

    # Project Management
    WORKSPACE_ROOT: str | None = Field(default=None, validation_alias="WORKSPACE_ROOT")

    # Artifacts (Relative to ~/.evoloop in home dir for persistence, or subfolder of WORKSPACE_ROOT?)
    # Decision: Keep them in user app data dir to avoid cluttering projects root or ephemeral CWD.
    @computed_field
    @property
    def APP_DATA_DIR(self) -> str:
        """Centralized application data directory."""
        return os.path.join(os.path.expanduser("~"), ".evoloop")

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

    @computed_field
    @property
    def LIBRARY_ROOT(self) -> str:
        """Root directory for global knowledge base files."""
        path = os.path.join(self.APP_DATA_DIR, "library")
        os.makedirs(path, exist_ok=True)
        return path

    # Logic Limits
    MEMORY_SEARCH_LIMIT: int = 5
    RESEARCH_MAX_ITERATIONS: int = 5
    TREE_VIEW_MAX_LINES: int = 1500
    RECURSION_LIMIT: int = 100  # Default LangGraph recursion limit

    # Meta-Evolution
    # ENABLE_SELF_EVOLUTION removed

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
    WORKER_AGENT_MAX_STEPS: int = 100
    FINISH_AGENT_MAX_STEPS: int = 10

    @computed_field
    @property
    def CHECKPOINTER_DATABASE_URI(self) -> str:
        # Client mode: Use SQLite for checkpointer
        return self.DATABASE_URI

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
        return self


settings = Settings()  # type: ignore
