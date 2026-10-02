from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_workshop.audit.models import AuditEvent, AuditOutcome
from ai_workshop.audit.store import AuditStore


def store(tmp_path: Path) -> AuditStore:
    return AuditStore(tmp_path / "audit.jsonl")


def event(
    *,
    actor: str = "agent-titan",
    project: str | None = "project-alpha",
    run: str | None = "run-1",
    action: str = "git.push",
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    timestamp: datetime | None = None,
    message: str = "",
    attributes: dict[str, str] | None = None,
    sensitive_values: tuple[str, ...] = (),
) -> AuditEvent:
    return AuditEvent(
        actor_principal_id=actor,
        owner_principal_id="user-gracie",
        run_id=run,
        project_id=project,
        action=action,
        resource="origin/main",
        outcome=outcome,
        timestamp=timestamp or datetime.now(timezone.utc),
        message=message,
        attributes=attributes or {},
        sensitive_values=sensitive_values,
    )


def test_record_is_append_only_and_survives_reload(tmp_path: Path):
    audit = store(tmp_path)
    first = event(action="git.fetch")
    second = event(action="git.push")

    audit.record(first)
    first_line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()[0]
    audit.record(second)

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == first_line

    reloaded = store(tmp_path)
    assert [item.action for item in reloaded.query()] == ["git.fetch", "git.push"]


def test_query_filters_actor_project_run_and_action(tmp_path: Path):
    audit = store(tmp_path)
    audit.record(event(actor="agent-titan", project="a", run="run-a", action="git.push"))
    audit.record(event(actor="agent-review", project="a", run="run-b", action="git.diff"))
    audit.record(event(actor="agent-titan", project="b", run="run-c", action="git.diff"))

    assert len(audit.query(actor_principal_id="agent-titan")) == 2
    assert len(audit.query(project_id="a")) == 2
    assert [item.run_id for item in audit.query(action="git.diff")] == ["run-b", "run-c"]
    assert [item.action for item in audit.query(run_id="run-a")] == ["git.push"]


def test_query_filters_timestamp_range(tmp_path: Path):
    audit = store(tmp_path)
    base = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    audit.record(event(action="one", timestamp=base))
    audit.record(event(action="two", timestamp=base + timedelta(minutes=5)))
    audit.record(event(action="three", timestamp=base + timedelta(minutes=10)))

    result = audit.query(
        start_time=base + timedelta(minutes=1),
        end_time=base + timedelta(minutes=9),
    )

    assert [item.action for item in result] == ["two"]


def test_audit_never_records_secret_values(tmp_path: Path):
    audit = store(tmp_path)
    secret = "super-secret-token"
    audit.record(
        event(
            outcome=AuditOutcome.FAILURE,
            message=f"provider failed with token {secret}",
            attributes={
                "token": secret,
                "error": f"Authorization: Bearer {secret}",
                "status": "401",
            },
            sensitive_values=(secret,),
        )
    )

    raw = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert secret not in raw

    recorded = audit.query()[0]
    assert secret not in recorded.model_dump_json()
    assert recorded.attributes["token"] == "[REDACTED]"
    assert "[REDACTED]" in recorded.attributes["error"]
    assert "[REDACTED]" in recorded.message
    assert recorded.sensitive_values == ()


def test_sensitive_attribute_keys_are_redacted_without_explicit_value_list(tmp_path: Path):
    audit = store(tmp_path)
    audit.record(
        event(
            attributes={
                "password": "never-store-me",
                "api_key": "also-never-store-me",
                "status": "failed",
            }
        )
    )

    raw = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "never-store-me" not in raw
    assert "also-never-store-me" not in raw
    recorded = audit.query()[0]
    assert recorded.attributes["password"] == "[REDACTED]"
    assert recorded.attributes["api_key"] == "[REDACTED]"
    assert recorded.attributes["status"] == "failed"
