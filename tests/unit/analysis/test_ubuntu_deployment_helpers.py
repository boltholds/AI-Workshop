from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]


def test_all_deployment_scripts_have_valid_bash_syntax():
    scripts = [
        'scripts/install-ghidra-pinned.sh',
        'scripts/install-tunnel-systemd.sh',
        'scripts/deploy-ubuntu-analysis-worker.sh',
    ]
    for relative in scripts:
        script = ROOT / relative
        assert script.is_file()
        subprocess.run(['bash', '-n', str(script)], check=True)


def test_ghidra_runtime_is_full_jdk():
    worker = (ROOT / 'analysis/Dockerfile').read_text()
    assert 'FROM eclipse-temurin:21-jdk-noble' in worker
    assert '21-jre-noble' not in worker


def test_opt_in_rollout_never_removes_or_recreates_legacy_services():
    script = (ROOT / 'scripts/deploy-ubuntu-analysis-worker.sh').read_text()
    assert '--no-deps --no-build analysis-worker' in script
    assert '--no-deps --no-build gateway' in script
    assert 'compose up -d --no-deps --no-build gateway' in script
    assert 'gateway-state.tar.gz' in script
    assert 'previous-gateway-image.txt' in script
    assert '--remove-orphans' not in script
    assert 'compose down' not in script
    assert 'docker volume rm' not in script


def test_ghidra_installer_pins_official_release_hash():
    script = (ROOT / 'scripts/install-ghidra-pinned.sh').read_text()
    assert 'ghidra_12.1.4_PUBLIC_20260921.zip' in script
    assert 'ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db' in script
    assert 'sha256sum --check --status' in script
