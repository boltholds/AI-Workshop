from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VendorManifest:
    adapter_id: str
    source_url: str
    ref: str
    subtree: str
    sha256: str


class CloneRunner(Protocol):
    def clone(self, source_url: str, ref: str, destination: Path) -> None: ...


class GitCloneRunner:
    def clone(self, source_url: str, ref: str, destination: Path) -> None:
        try:
            completed = subprocess.run(
                [
                    "git", "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    "--depth", "1",
                    "--quiet",
                    "--branch", ref,
                    source_url,
                    str(destination),
                ],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                env={"PATH": __import__("os").environ.get("PATH", ""), "GIT_TERMINAL_PROMPT": "0"},
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("vendor clone timed out") from exc
        if completed.returncode != 0:
            raise RuntimeError("vendor clone failed")
        checkout = subprocess.run(
            ["git", "-C", str(destination), "checkout", "--quiet"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env={"PATH": __import__("os").environ.get("PATH", ""), "GIT_TERMINAL_PROMPT": "0"},
        )
        if checkout.returncode != 0:
            raise RuntimeError("vendor checkout failed")


class GitSubtreeVendor:
    MANIFEST_NAME = ".ai-workshop-vendor.json"

    def __init__(
        self,
        *,
        adapter_id: str,
        source_url: str,
        subtree: str,
        runner: CloneRunner | None = None,
    ):
        self.adapter_id = adapter_id
        self.source_url = source_url
        self.subtree = subtree.strip("/")
        self.runner = runner or GitCloneRunner()

    def vendor(self, ref: str, destination: Path) -> VendorManifest:
        ref = ref.strip()
        if not ref:
            raise ValueError("a pinned ref is required")
        destination = destination.resolve()

        existing = self._read_manifest(destination)
        if existing is not None and self._matches(existing, ref):
            current = self._checksum(destination)
            if current == existing.sha256:
                return existing

        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="ai-workshop-vendor-", dir=destination.parent) as temp_dir:
            clone_root = Path(temp_dir) / "repo"
            self.runner.clone(self.source_url, ref, clone_root)
            source = (clone_root / self.subtree).resolve()
            try:
                source.relative_to(clone_root.resolve())
            except ValueError as exc:
                raise ValueError("vendor subtree resolves outside clone root") from exc
            if not source.is_dir():
                raise ValueError(f"vendor subtree not found: {self.subtree}")
            self._reject_symlinks(source)
            shutil.copytree(source, destination)

        digest = self._checksum(destination)
        manifest = VendorManifest(
            adapter_id=self.adapter_id,
            source_url=self.source_url,
            ref=ref,
            subtree=self.subtree,
            sha256=digest,
        )
        (destination / self.MANIFEST_NAME).write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    def _read_manifest(self, destination: Path) -> VendorManifest | None:
        path = destination / self.MANIFEST_NAME
        if not path.is_file():
            return None
        try:
            return VendorManifest(**json.loads(path.read_text(encoding="utf-8")))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def _matches(self, manifest: VendorManifest, ref: str) -> bool:
        return (
            manifest.adapter_id == self.adapter_id
            and manifest.source_url == self.source_url
            and manifest.ref == ref
            and manifest.subtree == self.subtree
        )

    @classmethod
    def _checksum(cls, destination: Path) -> str:
        digest = sha256()
        for path in sorted(destination.rglob("*")):
            if not path.is_file() or path.name == cls.MANIFEST_NAME:
                continue
            relative = path.relative_to(destination).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            data = path.read_bytes()
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
        return digest.hexdigest()

    @staticmethod
    def _reject_symlinks(root: Path) -> None:
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"vendor subtree contains symlink: {path.relative_to(root)}")
