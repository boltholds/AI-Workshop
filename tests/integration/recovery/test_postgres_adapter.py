from pathlib import Path

from ai_workshop.recovery.adapters.postgres import PostgresAdapter, PostgresTarget


class CapturingExecutor:
    def __init__(self):
        self.calls = []

    def run(self, argv: list[str], *, env: dict[str, str]) -> None:
        self.calls.append((list(argv), dict(env)))
        if argv[0] == "pg_dump":
            destination = Path(argv[argv.index("--file") + 1])
            destination.write_bytes(b"postgres-dump")


def test_postgres_reference_adapter_uses_fixed_argv_and_secret_env(tmp_path: Path):
    executor = CapturingExecutor()
    adapter = PostgresAdapter(
        {
            "primary": PostgresTarget(
                host="127.0.0.1",
                port=5432,
                database="app",
                user="workshop",
                password="secret",
            )
        },
        executor=executor,
    )
    artifact = tmp_path / "dump.pgcustom"
    adapter.snapshot("primary", artifact)

    argv, env = executor.calls[-1]
    assert argv[0] == "pg_dump"
    assert "--format=custom" in argv
    assert "--file" in argv
    assert "secret" not in " ".join(argv)
    assert env["PGPASSWORD"] == "secret"
    assert artifact.read_bytes() == b"postgres-dump"

    adapter.restore("primary", artifact)
    argv, env = executor.calls[-1]
    assert argv[0] == "pg_restore"
    assert "--clean" in argv and "--if-exists" in argv
    assert argv[-1] == str(artifact)
    assert env["PGPASSWORD"] == "secret"
