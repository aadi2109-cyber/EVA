import os
from alembic import context
from sqlalchemy import create_engine, pool


def _url() -> str:
    x = context.get_x_argument(as_dictionary=True).get("url")
    return x or f"sqlite:///{os.getenv('GUARD_DB_PATH', './guard.db')}"


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
