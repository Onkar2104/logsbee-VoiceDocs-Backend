# from logging.config import fileConfig

# from alembic import context
# from sqlalchemy import engine_from_config, pool

# from app.core.config import settings
# from app.db.base import Base
# from app.models.document import Document, DocumentShare
from app.models.document_format_version import DocumentFormatVersion
# from app.models.google_drive import AudioRecording, GoogleDriveConnection, GoogleOAuthState
# from app.models.user_preferences import UserPreferences
# from app.models.user_settings import UserSettings

# config = context.config
# config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

# target_metadata = Base.metadata


# def run_migrations_offline() -> None:
#     context.configure(
#         url=settings.database_url,
#         target_metadata=target_metadata,
#         literal_binds=True,
#         dialect_opts={"paramstyle": "named"},
#         compare_type=True,
#     )
#     with context.begin_transaction():
#         context.run_migrations()


# def run_migrations_online() -> None:
#     connectable = engine_from_config(
#         config.get_section(config.config_ini_section, {}),
#         prefix="sqlalchemy.",
#         poolclass=pool.NullPool,
#     )
#     with connectable.connect() as connection:
#         context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
#         with context.begin_transaction():
#             context.run_migrations()


# if context.is_offline_mode():
#     run_migrations_offline()
# else:
#     run_migrations_online()




from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base

# Import all models so Alembic can detect their tables.
from app.models.document import Document, DocumentShare
from app.models.google_drive import (
    AudioRecording,
    GoogleDriveConnection,
    GoogleOAuthState,
)
from app.models.user_preferences import UserPreferences
from app.models.user_settings import UserSettings


config = context.config


def get_database_url() -> str:
    """Ensure PostgreSQL uses psycopg 3."""
    url = str(settings.database_url)

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


database_url = get_database_url()

# Escape percent signs because Alembic uses ConfigParser internally.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()