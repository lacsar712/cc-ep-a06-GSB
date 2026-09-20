import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB

from app.cqrs import (
    ConflictError,
    DomainError,
    add_tags,
    list_events,
    rebuild_projection_from_events,
    remove_tags,
    start_run,
)
from app.database import Base, get_db
from app.main import app
from app.models import RunProjection


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, compiler, **kw):
    return "JSON"


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


@pytest.fixture()
def client(db):
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    # Constructed without a context manager on purpose: entering it triggers
    # the lifespan, which targets the configured Postgres engine.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def researcher_token(client):
    resp = client.post(
        "/api/auth/login", json={"username": "researcher", "password": "lab123456"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture()
def auditor_token(client):
    resp = client.post(
        "/api/auth/login", json={"username": "auditor", "password": "audit123456"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _make_running_run(db) -> RunProjection:
    return start_run(
        db,
        actor="researcher",
        project="p1",
        name="night experiment",
        dataset_content_sha256=sha("ds-tags"),
        code_commit_sha="abc1234",
        description=None,
    )


# ---------- domain layer ----------

def test_add_tags_appends_event_and_projection(db):
    run = _make_running_run(db)
    run = add_tags(
        db, run_id=run.id, actor="researcher",
        tags=["night-run", "gpu"], expected_version=1,
    )
    assert run.tags_json == ["night-run", "gpu"]
    assert run.version == 2

    events = list_events(db, run.id)
    assert [e.event_type for e in events] == ["RunStarted", "RunTagsAdded"]
    assert events[-1].payload_json == {"tags": ["night-run", "gpu"]}


def test_add_tags_dedupes_existing(db):
    run = _make_running_run(db)
    add_tags(db, run_id=run.id, actor="r", tags=["night-run"], expected_version=1)
    with pytest.raises(DomainError):
        add_tags(db, run_id=run.id, actor="r", tags=["night-run"], expected_version=2)
    # duplicated/whitespace tags within one command collapse to one event
    run = add_tags(
        db, run_id=run.id, actor="r",
        tags=["gpu", " gpu ", "night-run"], expected_version=2,
    )
    assert run.tags_json == ["night-run", "gpu"]


def test_remove_tags(db):
    run = _make_running_run(db)
    add_tags(db, run_id=run.id, actor="r", tags=["night-run", "gpu"], expected_version=1)
    run = remove_tags(
        db, run_id=run.id, actor="r", tags=["gpu"], expected_version=2,
    )
    assert run.tags_json == ["night-run"]
    assert run.version == 3


def test_tags_allowed_after_completion(db):
    run = _make_running_run(db)
    from app.cqrs import complete_run

    run = complete_run(
        db, run_id=run.id, actor="r", result_summary="done", expected_version=1
    )
    run = add_tags(
        db, run_id=run.id, actor="r", tags=["archived"], expected_version=2
    )
    assert run.status == "completed"
    assert run.tags_json == ["archived"]


def test_tags_optimistic_lock_conflict(db):
    run = _make_running_run(db)
    with pytest.raises(ConflictError):
        add_tags(
            db, run_id=run.id, actor="r", tags=["x"], expected_version=99,
        )


def test_invalid_tag_rejected(db):
    run = _make_running_run(db)
    with pytest.raises(DomainError):
        add_tags(db, run_id=run.id, actor="r", tags=["bad tag"], expected_version=1)


def test_tag_events_replay(db):
    run = _make_running_run(db)
    add_tags(db, run_id=run.id, actor="r", tags=["night-run", "gpu"], expected_version=1)
    remove_tags(db, run_id=run.id, actor="r", tags=["gpu"], expected_version=2)

    rebuilt = rebuild_projection_from_events(db, run.id)
    assert rebuilt.tags_json == ["night-run"]
    assert rebuilt.version == 3


# ---------- API layer ----------

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_researcher_can_tag_and_filter(client, db, researcher_token):
    run = _make_running_run(db)

    resp = client.post(
        f"/api/runs/{run.id}/tags",
        json={"tags": ["night-run"], "expected_version": 1},
        headers=_auth(researcher_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tags_json"] == ["night-run"]

    # server-side filter: only the tagged run comes back
    _make_running_run(db)
    filtered = client.get("/api/runs?tag=night-run", headers=_auth(researcher_token))
    assert filtered.status_code == 200
    data = filtered.json()
    assert len(data) == 1
    assert data[0]["id"] == str(run.id)

    unfiltered = client.get("/api/runs", headers=_auth(researcher_token))
    assert len(unfiltered.json()) == 2

    # tag aggregation endpoint
    tags_resp = client.get("/api/tags", headers=_auth(researcher_token))
    assert tags_resp.status_code == 200
    assert {"tag": "night-run", "count": 1} in tags_resp.json()


def test_auditor_cannot_modify_tags(client, db, auditor_token):
    run = _make_running_run(db)
    resp = client.post(
        f"/api/runs/{run.id}/tags",
        json={"tags": ["night-run"], "expected_version": 1},
        headers=_auth(auditor_token),
    )
    assert resp.status_code == 403

    resp = client.request(
        "DELETE",
        f"/api/runs/{run.id}/tags",
        json={"tags": ["night-run"], "expected_version": 1},
        headers=_auth(auditor_token),
    )
    assert resp.status_code == 403

    # auditor can still see tags (empty here)
    visible = client.get("/api/runs", headers=_auth(auditor_token))
    assert visible.status_code == 200
    assert visible.json()[0]["tags_json"] == []


def test_delete_tags_endpoint(client, db, researcher_token):
    run = _make_running_run(db)
    client.post(
        f"/api/runs/{run.id}/tags",
        json={"tags": ["night-run"], "expected_version": 1},
        headers=_auth(researcher_token),
    )
    resp = client.request(
        "DELETE",
        f"/api/runs/{run.id}/tags",
        json={"tags": ["night-run"], "expected_version": 2},
        headers=_auth(researcher_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tags_json"] == []
