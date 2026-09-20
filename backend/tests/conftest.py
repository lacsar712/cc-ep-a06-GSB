import pytest
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base


# JSONB not available on SQLite — compile as JSON for tests
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, compiler, **kw):
    return "JSON"


# PG UUID renders as "UUID" on SQLite, whose NUMERIC affinity would coerce
# all-digit uuid strings (e.g. seed ids 11111111-...) to floats — force TEXT affinity
@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(_type, compiler, **kw):
    return "CHAR(32)"


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
