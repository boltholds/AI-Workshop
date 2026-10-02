from __future__ import annotations

import json
from pathlib import Path
import threading

from ai_workshop.forge.models import (
    ForgeProfile,
    ForgeProviderKind,
    ForgeRepositoryBinding,
    ForgeTransportSecurity,
)


class ForgeRegistry:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._profiles: dict[str, ForgeProfile] = {}
        self._bindings: dict[str, ForgeRepositoryBinding] = {}
        self._load()

    def create_profile(self, profile: ForgeProfile) -> ForgeProfile:
        with self._lock:
            if profile.profile_id in self._profiles:
                raise ValueError(
                    f"forge profile already exists: {profile.profile_id}"
                )
            self._profiles[profile.profile_id] = profile
            try:
                self._persist()
            except Exception:
                self._profiles.pop(profile.profile_id, None)
                raise
            return profile

    def get_profile(self, profile_id: str) -> ForgeProfile:
        with self._lock:
            profile = self._profiles.get(profile_id)
            if profile is None:
                raise KeyError(f"unknown forge profile: {profile_id}")
            return profile

    def list_profiles(self) -> list[ForgeProfile]:
        with self._lock:
            return [self._profiles[key] for key in sorted(self._profiles)]

    def bind_project(
        self,
        binding: ForgeRepositoryBinding,
    ) -> ForgeRepositoryBinding:
        with self._lock:
            if binding.profile_id not in self._profiles:
                raise KeyError(
                    f"unknown forge profile: {binding.profile_id}"
                )
            if binding.project_id in self._bindings:
                raise ValueError(
                    f"project already bound to forge: {binding.project_id}"
                )
            self._bindings[binding.project_id] = binding
            try:
                self._persist()
            except Exception:
                self._bindings.pop(binding.project_id, None)
                raise
            return binding

    def project_binding(
        self,
        project_id: str,
    ) -> ForgeRepositoryBinding:
        with self._lock:
            binding = self._bindings.get(project_id)
            if binding is None:
                raise KeyError(
                    f"project has no forge binding: {project_id}"
                )
            return binding

    def list_bindings(self) -> list[ForgeRepositoryBinding]:
        with self._lock:
            return [self._bindings[key] for key in sorted(self._bindings)]

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported forge registry version")

        raw_profiles = payload.get("profiles", [])
        if not isinstance(raw_profiles, list):
            raise ValueError("forge profiles must be a list")
        for raw in raw_profiles:
            profile = ForgeProfile.model_validate(raw)
            if profile.profile_id in self._profiles:
                raise ValueError("duplicate forge profile")
            self._profiles[profile.profile_id] = profile

        raw_bindings = payload.get("bindings", [])
        if not isinstance(raw_bindings, list):
            raise ValueError("forge bindings must be a list")
        for raw in raw_bindings:
            binding = ForgeRepositoryBinding.model_validate(raw)
            if binding.profile_id not in self._profiles:
                raise ValueError("forge binding references unknown profile")
            if binding.project_id in self._bindings:
                raise ValueError("duplicate project forge binding")
            self._bindings[binding.project_id] = binding

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "profiles": [
                self._profiles[key].model_dump(mode="json")
                for key in sorted(self._profiles)
            ],
            "bindings": [
                self._bindings[key].model_dump(mode="json")
                for key in sorted(self._bindings)
            ],
        }
        temporary = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
