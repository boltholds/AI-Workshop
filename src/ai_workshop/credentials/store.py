from __future__ import annotations

import json
from pathlib import Path
import stat
import threading

from ai_workshop.credentials.git_env import GitCredentialContext
from ai_workshop.credentials.models import (
    CredentialKind,
    CredentialProfile,
    HttpsTokenCredentialProfile,
    SshCredentialProfile,
)


class CredentialStore:
    def __init__(
        self,
        *,
        state_path: Path,
        secret_root: Path,
        forbidden_roots: tuple[Path, ...] = (),
    ):
        self.state_path = Path(state_path)
        self.secret_root = Path(secret_root).expanduser().resolve()
        self.forbidden_roots = tuple(
            Path(root).expanduser().resolve() for root in forbidden_roots
        )
        self._validate_secret_root()
        self.secret_root.mkdir(parents=True, exist_ok=True)
        try:
            self.secret_root.chmod(stat.S_IRWXU)
        except OSError:
            pass
        self._lock = threading.RLock()
        self._profiles: dict[str, CredentialProfile] = {}
        self._load()

    def create_ssh(
        self,
        credential_id: str,
        *,
        private_key: str,
    ) -> SshCredentialProfile:
        profile = SshCredentialProfile(credential_id=credential_id)
        self._create(profile, private_key)
        return profile

    def create_https_token(
        self,
        credential_id: str,
        *,
        username: str,
        token: str,
    ) -> HttpsTokenCredentialProfile:
        profile = HttpsTokenCredentialProfile(
            credential_id=credential_id,
            username=username,
        )
        self._create(profile, token)
        return profile

    def get(self, credential_id: str) -> CredentialProfile:
        with self._lock:
            profile = self._profiles.get(credential_id)
            if profile is None:
                raise KeyError(f"unknown credential profile: {credential_id}")
            return profile

    def list(self) -> list[CredentialProfile]:
        with self._lock:
            return [self._profiles[key] for key in sorted(self._profiles)]

    def secret_path(self, credential_id: str) -> Path:
        profile = self.get(credential_id)
        suffix = "private-key" if isinstance(profile, SshCredentialProfile) else "token"
        path = (self.secret_root / credential_id / suffix).resolve()
        self._require_within(path, self.secret_root, "credential secret path escapes secret root")
        return path

    def git_context(self, credential_id: str) -> GitCredentialContext:
        profile = self.get(credential_id)
        path = self.secret_path(credential_id)
        if not path.is_file():
            raise FileNotFoundError(f"credential secret is unavailable: {credential_id}")
        return GitCredentialContext(profile, path)

    def _create(self, profile: CredentialProfile, secret: str) -> None:
        if not secret:
            raise ValueError("credential secret must not be empty")
        if "\x00" in secret:
            raise ValueError("credential secret contains NUL")
        with self._lock:
            if profile.credential_id in self._profiles:
                raise ValueError(
                    f"credential profile already exists: {profile.credential_id}"
                )
            directory = (self.secret_root / profile.credential_id).resolve()
            self._require_within(
                directory,
                self.secret_root,
                "credential secret path escapes secret root",
            )
            directory.mkdir(parents=True, exist_ok=False)
            try:
                directory.chmod(stat.S_IRWXU)
            except OSError:
                pass

            suffix = (
                "private-key"
                if isinstance(profile, SshCredentialProfile)
                else "token"
            )
            secret_path = directory / suffix
            secret_path.write_text(secret, encoding="utf-8")
            try:
                secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

            self._profiles[profile.credential_id] = profile
            try:
                self._persist()
            except Exception:
                self._profiles.pop(profile.credential_id, None)
                try:
                    secret_path.unlink()
                    directory.rmdir()
                except OSError:
                    pass
                raise

    def _validate_secret_root(self) -> None:
        for forbidden in self.forbidden_roots:
            if self._overlap(self.secret_root, forbidden):
                raise ValueError("credential secret root overlaps forbidden storage")

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported credential registry version")
        raw_profiles = payload.get("profiles", [])
        if not isinstance(raw_profiles, list):
            raise ValueError("credential profiles must be a list")

        loaded: dict[str, CredentialProfile] = {}
        for raw in raw_profiles:
            kind = raw.get("kind") if isinstance(raw, dict) else None
            if kind == CredentialKind.SSH.value:
                profile: CredentialProfile = SshCredentialProfile.model_validate(raw)
            elif kind == CredentialKind.HTTPS_TOKEN.value:
                profile = HttpsTokenCredentialProfile.model_validate(raw)
            else:
                raise ValueError("unknown credential profile kind")
            if profile.credential_id in loaded:
                raise ValueError(f"duplicate credential profile: {profile.credential_id}")
            loaded[profile.credential_id] = profile
        self._profiles = loaded

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "profiles": [
                self._profiles[key].model_dump(mode="json")
                for key in sorted(self._profiles)
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    @staticmethod
    def _overlap(left: Path, right: Path) -> bool:
        if left == right:
            return True
        try:
            left.relative_to(right)
            return True
        except ValueError:
            pass
        try:
            right.relative_to(left)
            return True
        except ValueError:
            return False

    @staticmethod
    def _require_within(path: Path, root: Path, message: str) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(message) from exc
