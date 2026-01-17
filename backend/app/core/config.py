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
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
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

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    DB_ECHO: bool = False # Added for EvoLoop compatibility

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

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
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    # --- EvoLoop Configuration ---
    APP_ENV: Literal["development", "production", "testing"] = "development"
    LOG_LEVEL: str = "INFO"

    # Graph (Neo4j)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str | None = None

    # Cache (Redis)
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM Providers
    OPENAI_API_KEY: str = "sk-dummy-key-for-local-dev"
    OPENAI_BASE_URL: str = "http://localhost:1234/v1"
    OPENAI_MODEL_NAME: str = "gpt-4o"
    
    # Embedding Configuration
    EMBEDDING_PROVIDER: Literal["openai", "ollama", "dashscope", "huggingface", "local"] = "openai"
    EMBEDDING_BASE_URL: str | None = None # Optional override
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small" # Qwen / Aliyun Compatible
    EMBEDDING_DIMENSIONS: int = 768 # Nomic / Local Default

    ANTHROPIC_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None
    BRAVE_API_KEY: str | None = None

    # Local LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # General Agent / Intention
    GENERAL_AGENT_MODEL: str = "gpt-4o"

    # Browser Agent
    BROWSER_USE_API_KEY: str = "sk-dummy-key-for-local-dev"
    BROWSER_MODEL_NAME: str | None = "gpt-4o"

    # Computer Agent (Agent S)
    OS_PROVIDER: str = "openai"
    OS_MODEL: str = "gpt-4o"
    OS_GROUND_PROVIDER: str = "huggingface"
    OS_GROUND_URL: str | None = "http://localhost:8080"
    OS_GROUND_MODEL: str = "ui-tars-1.5-7b"
    OS_GROUND_API_KEY: str | None = None

    # Mobile Agent (AutoGLM)
    PHONE_AGENT_BASE_URL: str = "http://localhost:8000/v1"
    PHONE_AGENT_MODEL: str = "autoglm-phone-9b"
    PHONE_AGENT_DEVICE_ID: str | None = None
    PHONE_AGENT_LANG: Literal["cn", "en"] = "cn"

    # EvoCloud API
    EVOCLOUD_API_URL: str = Field("https://mall.imagicbox.cn", validation_alias="EVOCLOUD_API_URL")
    EVOCLOUD_WS_URL: str = Field("wss://mall.imagicbox.cn/wss/", validation_alias="EVOCLOUD_WS_URL")
    EVOCLOUD_API_KEY: str | None = Field(None, validation_alias="EVOCLOUD_API_KEY")
    EVOCLOUD_API_SECRET: str | None = Field(None, validation_alias="EVOCLOUD_API_SECRET")

    # Client / Device Info
    EVOCLOUD_ACCESS_TOKEN: str | None = Field(None, validation_alias="EVOCLOUD_ACCESS_TOKEN")
    EVOCLOUD_DEVICE_NAME: str | None = Field("EvoLoop-Desktop", validation_alias="EVOCLOUD_DEVICE_NAME")

    # Project Management
    # Logic to find default projects root:
    # 1. ~/项目 (Chinese optimized)
    # 2. ~/Projects (Standard)
    # 3. ~/projects (Standard lower)
    # 4. ~ (Home)
    def _default_projects_root():
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "项目"),
            os.path.join(home, "Projects"),
            os.path.join(home, "projects")
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return home

    PROJECTS_ROOT: str = Field(default_factory=_default_projects_root, validation_alias="PROJECTS_ROOT")

    # Artifacts (Relative to .gemini/evoloop in home dir for persistence, or subfolder of PROJECTS_ROOT?)
    # Decision: Keep them in user app data dir to avoid cluttering projects root or ephemeral CWD.
    @computed_field
    @property
    def APP_DATA_DIR(self) -> str:
        """Centralized application data directory."""
        return os.path.join(os.path.expanduser("~"), ".gemini", "evoloop")

    @computed_field
    @property
    def BROWSER_ARTIFACTS_DIR(self) -> str:
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "browser")
        os.makedirs(path, exist_ok=True)
        return path

    @computed_field
    @property
    def SCREENSHOTS_DIR(self) -> str:
        path = os.path.join(self.APP_DATA_DIR, "artifacts", "screenshots")
        os.makedirs(path, exist_ok=True)
        return path


    # Logic Limits
    MEMORY_SEARCH_LIMIT: int = 5
    RESEARCH_MAX_ITERATIONS: int = 5
    TREE_VIEW_MAX_LINES: int = 1500
    RECURSION_LIMIT: int = 100  # Default LangGraph recursion limit

    # Meta-Evolution
    ENABLE_SELF_EVOLUTION: bool = False # Dangerous! Requires sandbox.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def CHECKPOINTER_DATABASE_URI(self) -> str:
        # Re-use Postgres DSN for Checkpointer
        return str(PostgresDsn.build(
            scheme="postgresql",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
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
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)


        return self


settings = Settings()  # type: ignore
