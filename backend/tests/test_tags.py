import hashlib

import pytest

from app.cqrs import (
    ConflictError,
    DomainError,
    complete_run,
    list_events,
    list_tags,
    rebuild_tags_from_events,
    start_run,
    tag_run,
    untag_run,
)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def make_run(db, name="n1"):
    return start_run(
        db,
        actor="researcher",
        project="p1",
        name=name,
        dataset_content_sha256=sha(f"ds-{name}"),
        code_commit_sha="abc1234",
        description=None,
    )


def test_tag_run_appends_event_and_projects(db):
    run = make_run(db)
    run = tag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=1)

    assert run.version == 2
    assert list_tags(db, run.id) == ["night-run"]

    events = list_events(db, run.id)
    assert [e.event_type for e in events] == ["RunStarted", "RunTagged"]
    assert events[-1].payload_json == {"tag": "night-run"}
    assert events[-1].actor == "researcher"


def test_tag_multiple_and_dedup_idempotent(db):
    run = make_run(db)
    run = tag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=1)
    run = tag_run(db, run_id=run.id, actor="researcher", tag="gpu", expected_version=2)
    assert list_tags(db, run.id) == ["gpu", "night-run"]

    # 重复打同一标签:幂等空操作,不追加事件、版本不变
    run = tag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=3)
    assert run.version == 3
    assert list_tags(db, run.id) == ["gpu", "night-run"]
    assert [e.event_type for e in list_events(db, run.id)] == [
        "RunStarted",
        "RunTagged",
        "RunTagged",
    ]


def test_tag_normalizes_whitespace(db):
    run = make_run(db)
    tag_run(db, run_id=run.id, actor="researcher", tag="  night-run  ", expected_version=1)
    assert list_tags(db, run.id) == ["night-run"]


def test_tag_rejects_empty_and_too_long(db):
    run = make_run(db)
    with pytest.raises(DomainError):
        tag_run(db, run_id=run.id, actor="researcher", tag="   ", expected_version=1)
    with pytest.raises(DomainError):
        tag_run(db, run_id=run.id, actor="researcher", tag="x" * 65, expected_version=1)


def test_untag_run_removes_and_is_idempotent(db):
    run = make_run(db)
    run = tag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=1)
    run = untag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=2)
    assert run.version == 3
    assert list_tags(db, run.id) == []
    assert [e.event_type for e in list_events(db, run.id)] == [
        "RunStarted",
        "RunTagged",
        "RunUntagged",
    ]

    # 移除不存在的标签:幂等空操作
    run = untag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=3)
    assert run.version == 3
    assert len(list_events(db, run.id)) == 3


def test_tag_optimistic_lock_conflict(db):
    run = make_run(db)
    with pytest.raises(ConflictError):
        tag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=0)
    with pytest.raises(ConflictError):
        untag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=7)


def test_tag_missing_run_404(db):
    from uuid import uuid4

    with pytest.raises(DomainError) as exc:
        tag_run(db, run_id=uuid4(), actor="researcher", tag="x", expected_version=1)
    assert exc.value.status_code == 404


def test_tag_allowed_on_terminal_run(db):
    run = make_run(db)
    run = complete_run(
        db, run_id=run.id, actor="researcher", result_summary="done", expected_version=1
    )
    # 标签是元数据,终态 Run 仍可打标/去标
    run = tag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=2)
    assert list_tags(db, run.id) == ["night-run"]


def test_tag_projection_matches_event_replay(db):
    run = make_run(db)
    run = tag_run(db, run_id=run.id, actor="researcher", tag="night-run", expected_version=1)
    run = tag_run(db, run_id=run.id, actor="researcher", tag="gpu", expected_version=2)
    run = untag_run(db, run_id=run.id, actor="researcher", tag="gpu", expected_version=3)
    run = tag_run(db, run_id=run.id, actor="researcher", tag="周末批", expected_version=4)

    assert list_tags(db, run.id) == rebuild_tags_from_events(db, run.id) == [
        "night-run",
        "周末批",
    ]
