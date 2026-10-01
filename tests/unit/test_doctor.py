from pathlib import Path

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.doctor import CheckSpec, Doctor, project_paths_check


def test_doctor_reports_component_specific_failure():
    report = Doctor([
        CheckSpec("gateway", required=True, probe=lambda: (False, "connection refused"), remediation="start gateway"),
        CheckSpec("browser", required=False, probe=lambda: (False, "not running"), remediation="start browser"),
        CheckSpec("docker", required=True, probe=lambda: (True, "ok"), remediation="install docker"),
    ]).run()

    assert report.healthy is False
    assert report.exit_code == 1
    assert report.by_name("gateway").healthy is False
    assert report.by_name("gateway").message == "connection refused"
    assert report.by_name("browser").required is False
    assert report.by_name("docker").healthy is True


def test_optional_component_failure_does_not_fail_doctor():
    report = Doctor([
        CheckSpec("workspace", required=True, probe=lambda: (True, "ok"), remediation="start workspace"),
        CheckSpec("browser", required=False, probe=lambda: (False, "not configured"), remediation="configure browser"),
    ]).run()
    assert report.healthy is True
    assert report.exit_code == 0
    assert report.by_name("browser").healthy is False


def test_project_path_check_reports_missing_mount_source(tmp_path: Path):
    config = WorkshopConfig(projects=[
        ProjectMount(
            project_id="missing",
            host=tmp_path / "does-not-exist",
            container="/workspace/missing",
            mode="rw",
        )
    ])
    check = project_paths_check(config)
    healthy, message = check.probe()
    assert healthy is False
    assert "missing" in message
