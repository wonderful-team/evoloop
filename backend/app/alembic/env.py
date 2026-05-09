from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# target_metadata = None

from app.models import SQLModel  # noqa
from app.core.config import settings # noqa
from app.infrastructure.database.sql.database import Base # noqa
# Import all models to ensure they are registered in metadata
from app import models # noqa

# ---------------------------------------------------------------------------
# Dual-database migration support (main db + vector db)
# Usage:
#   alembic upgrade head               # migrate main database
#   alembic -x database=vector upgrade head   # migrate vector database
# ---------------------------------------------------------------------------

cmd_opts = context.get_x_argument(as_dictionary=True)
_database_target = cmd_opts.get("database", "main")

if _database_target == "vector":
    # Vector-database migrations target the pgvector schema only.
    try:
        from app.infrastructure.database.vector.pgvector_store import VectorBase
        target_metadata = [VectorBase.metadata]
    except ImportError:
        target_metadata = None
else:
    target_metadata = [SQLModel.metadata, Base.metadata]

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    if _database_target == "vector":
        url = settings.VECTOR_DATABASE_URI
        if not url:
            raise RuntimeError(
                "VECTOR_DATABASE_URI is not configured. "
                "Set VECTOR_POSTGRES_* or run with database=main."
            )
    else:
        url = str(settings.SQLALCHEMY_DATABASE_URI)

    # Alembic runs in a synchronous context, so we need to use a synchronous driver.
    # Replace async drivers with their sync counterparts.
    if url and "sqlite+aiosqlite" in url:
        url = url.replace("sqlite+aiosqlite", "sqlite")
    if url and "postgresql+psycopg" in url:
        url = url.replace("postgresql+psycopg", "postgresql")
    return url


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
