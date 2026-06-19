from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, engine_from_config, pool, create_engine

from config import settings as app_settings
from app.core.database import Base
import app.models  # noqa: F401 - load models for autogenerate detection

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = URL.create(
    drivername="postgresql",
    username=app_settings.DB_USER,
    password=app_settings.DB_PASSWORD,
    host=app_settings.DB_HOST,
    port=app_settings.DB_PORT,
    database=app_settings.DB_NAME,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(db_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
