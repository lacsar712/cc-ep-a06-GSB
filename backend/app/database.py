from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def ensure_schema_patches() -> None:
    """Idempotent lightweight migrations for columns added after first release.

    create_all() only creates missing tables, never adds columns to an
    existing table, so evolving deployments (e.g. the tags_json column) are
    patched here on startup.
    """
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE run_projections "
                    "ADD COLUMN IF NOT EXISTS tags_json JSONB "
                    "NOT NULL DEFAULT '[]'::jsonb"
                )
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
