from pathlib import Path

import pytest

from ai_workshop.recovery.reset import ResetService


def make_service(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "cache"
    browser = tmp_path / "browser-artifacts"
    cache.mkdir()
    browser.mkdir()
    state_calls = []
    infrastructure_calls = []
    service = ResetService(
        cache_paths=[cache],
        browser_artifact_paths=[browser],
        state_resetters={"memory": lambda: state_calls.append("memory")},
        infrastructure_resetter=lambda: infrastructure_calls.append("reset"),
        project_roots=[project],
    )
    return service, project, cache, browser, state_calls, infrastructure_calls


def test_reset_plans_never_include_project_directories(tmp_path: Path):
    svc, project, cache, browser, _, _ = make_service(tmp_path)
    cache_plan = svc.plan("cache")
    browser_plan = svc.plan("browser-artifacts")
    assert str(project.resolve()) not in cache_plan.filesystem_paths
    assert str(project.resolve()) not in browser_plan.filesystem_paths
    assert cache_plan.filesystem_paths == [str(cache.resolve())]
    assert browser_plan.filesystem_paths == [str(browser.resolve())]


def test_no_implicit_projects_reset_scope(tmp_path: Path):
    svc, *_ = make_service(tmp_path)
    with pytest.raises(ValueError, match="unsupported reset scope"):
        svc.plan("projects")


def test_state_and_infrastructure_reset_are_explicit_and_confirmed(tmp_path: Path):
    svc, _, _, _, state_calls, infrastructure_calls = make_service(tmp_path)

    state_plan = svc.plan("state:memory")
    with pytest.raises(PermissionError, match="confirmation"):
        svc.execute(state_plan, "missing")
    state_token = svc.prepare(state_plan).token
    svc.execute(state_plan, state_token)
    assert state_calls == ["memory"]

    infra_plan = svc.plan("infrastructure")
    infra_token = svc.prepare(infra_plan).token
    svc.execute(infra_plan, infra_token)
    assert infrastructure_calls == ["reset"]


def test_reset_rejects_any_path_overlapping_a_project_root(tmp_path: Path):
    project = tmp_path / "workspace" / "project"
    project.mkdir(parents=True)
    with pytest.raises(ValueError, match="overlaps project root"):
        ResetService(
            cache_paths=[tmp_path / "workspace"],
            browser_artifact_paths=[],
            state_resetters={},
            infrastructure_resetter=None,
            project_roots=[project],
        )
