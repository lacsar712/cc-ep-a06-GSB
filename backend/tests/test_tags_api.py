import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.main import app


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # 不使用 with 语法,避免触发 lifespan 去连 PostgreSQL
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth_headers(username: str, role: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(username, role)}"}


RESEARCHER = auth_headers("researcher", "researcher")
AUDITOR = auth_headers("auditor", "auditor")


def create_run(client, name: str) -> dict:
    resp = client.post(
        "/api/runs",
        json={
            "project": "p1",
            "name": name,
            "dataset_content_sha256": sha(f"ds-{name}"),
            "code_commit_sha": "abc1234",
        },
        headers=RESEARCHER,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_acceptance_tag_and_server_side_filter(client):
    run_a = create_run(client, "run-A")
    run_b = create_run(client, "run-B")

    # 给进行中的 run-A 打上 night-run
    resp = client.post(
        f"/api/runs/{run_a['id']}/tags",
        json={"tag": "night-run", "expected_version": run_a["version"]},
        headers=RESEARCHER,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tags"] == ["night-run"]

    # 列表每行带 tags
    runs = client.get("/api/runs", headers=AUDITOR).json()
    assert len(runs) == 2
    tags_by_id = {r["id"]: r["tags"] for r in runs}
    assert tags_by_id[run_a["id"]] == ["night-run"]
    assert tags_by_id[run_b["id"]] == []

    # 按 night-run 过滤(服务端):只剩 run-A 这一条
    filtered = client.get("/api/runs", params={"tag": "night-run"}, headers=AUDITOR).json()
    assert [r["id"] for r in filtered] == [run_a["id"]]

    # 标签事件可回看
    events = client.get(f"/api/runs/{run_a['id']}/events", headers=AUDITOR).json()
    assert [e["event_type"] for e in events] == ["RunStarted", "RunTagged"]
    assert events[-1]["payload_json"] == {"tag": "night-run"}

    # 标签汇总入口
    tags = client.get("/api/tags", headers=AUDITOR).json()
    assert tags == [{"tag": "night-run", "run_count": 1}]

    # 去标后过滤结果为空
    run_a = client.get(f"/api/runs/{run_a['id']}", headers=RESEARCHER).json()
    resp = client.post(
        f"/api/runs/{run_a['id']}/untag",
        json={"tag": "night-run", "expected_version": run_a["version"]},
        headers=RESEARCHER,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tags"] == []
    assert client.get("/api/runs", params={"tag": "night-run"}, headers=AUDITOR).json() == []


def test_auditor_cannot_modify_tags(client):
    run = create_run(client, "run-A")
    for endpoint in ("tags", "untag"):
        resp = client.post(
            f"/api/runs/{run['id']}/{endpoint}",
            json={"tag": "night-run", "expected_version": run["version"]},
            headers=AUDITOR,
        )
        assert resp.status_code == 403, resp.text

    # 审计员可以查看标签
    client.post(
        f"/api/runs/{run['id']}/tags",
        json={"tag": "night-run", "expected_version": run["version"]},
        headers=RESEARCHER,
    )
    detail = client.get(f"/api/runs/{run['id']}", headers=AUDITOR)
    assert detail.status_code == 200
    assert detail.json()["tags"] == ["night-run"]


def test_tag_filter_combines_with_status(client):
    run_a = create_run(client, "run-A")
    run_b = create_run(client, "run-B")
    for run in (run_a, run_b):
        client.post(
            f"/api/runs/{run['id']}/tags",
            json={"tag": "night-run", "expected_version": run["version"]},
            headers=RESEARCHER,
        )
    # 完成 run-B(打标后 version=2)
    client.post(
        f"/api/runs/{run_b['id']}/complete",
        json={"result_summary": "done", "expected_version": 2},
        headers=RESEARCHER,
    )

    filtered = client.get(
        "/api/runs",
        params={"tag": "night-run", "status": "running"},
        headers=RESEARCHER,
    ).json()
    assert [r["id"] for r in filtered] == [run_a["id"]]


def test_tag_endpoints_require_auth(client):
    run = create_run(client, "run-A")
    resp = client.post(
        f"/api/runs/{run['id']}/tags",
        json={"tag": "x", "expected_version": 1},
    )
    assert resp.status_code == 401
    assert client.get("/api/tags").status_code == 401
