from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import threading
from typing import Protocol

from ai_workshop.authn.models import (
    BootstrapResult,
    CeremonyStart,
    PasskeyCredential,
    SessionToken,
    VerifiedAuthentication,
    VerifiedRegistration,
)
from ai_workshop.authn.sessions import SessionStore
from ai_workshop.identity.models import RoleDefinition, UserPrincipal
from ai_workshop.identity.protocol import PrincipalService


def _b64(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return urlsafe_b64decode(value + padding)


class WebAuthnBackend(Protocol):
    def registration_options(
        self,
        *,
        user_id: bytes,
        username: str,
        display_name: str,
        challenge: bytes,
        exclude_credentials: tuple[bytes, ...],
    ) -> str: ...

    def verify_registration(
        self,
        response: dict[str, object],
        *,
        expected_challenge: bytes,
    ) -> VerifiedRegistration: ...

    def authentication_options(
        self,
        *,
        challenge: bytes,
        allow_credentials: tuple[bytes, ...],
    ) -> str: ...

    def credential_id_from_response(
        self,
        response: dict[str, object],
    ) -> bytes: ...

    def verify_authentication(
        self,
        response: dict[str, object],
        *,
        expected_challenge: bytes,
        credential_public_key: bytes,
        credential_current_sign_count: int,
    ) -> VerifiedAuthentication: ...


class PyWebAuthnBackend:
    def __init__(self, *, rp_id: str, origin: str, rp_name: str):
        self.rp_id = rp_id
        self.origin = origin
        self.rp_name = rp_name

    def registration_options(
        self,
        *,
        user_id: bytes,
        username: str,
        display_name: str,
        challenge: bytes,
        exclude_credentials: tuple[bytes, ...],
    ) -> str:
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )

        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=user_id,
            user_name=username,
            user_display_name=display_name,
            challenge=challenge,
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=value)
                for value in exclude_credentials
            ],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        return options_to_json(options)

    def verify_registration(
        self,
        response: dict[str, object],
        *,
        expected_challenge: bytes,
    ) -> VerifiedRegistration:
        from webauthn import verify_registration_response

        verified = verify_registration_response(
            credential=response,
            expected_challenge=expected_challenge,
            expected_rp_id=self.rp_id,
            expected_origin=self.origin,
            require_user_verification=True,
        )
        return VerifiedRegistration(
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
        )

    def authentication_options(
        self,
        *,
        challenge: bytes,
        allow_credentials: tuple[bytes, ...],
    ) -> str:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import (
            PublicKeyCredentialDescriptor,
            UserVerificationRequirement,
        )

        options = generate_authentication_options(
            rp_id=self.rp_id,
            challenge=challenge,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=value)
                for value in allow_credentials
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return options_to_json(options)

    def credential_id_from_response(
        self,
        response: dict[str, object],
    ) -> bytes:
        from webauthn import base64url_to_bytes

        value = response.get("rawId") or response.get("id")
        if not isinstance(value, str) or not value:
            raise ValueError("WebAuthn response has no credential id")
        return base64url_to_bytes(value)

    def verify_authentication(
        self,
        response: dict[str, object],
        *,
        expected_challenge: bytes,
        credential_public_key: bytes,
        credential_current_sign_count: int,
    ) -> VerifiedAuthentication:
        from webauthn import verify_authentication_response

        verified = verify_authentication_response(
            credential=response,
            expected_challenge=expected_challenge,
            expected_rp_id=self.rp_id,
            expected_origin=self.origin,
            credential_public_key=credential_public_key,
            credential_current_sign_count=credential_current_sign_count,
            require_user_verification=True,
        )
        return VerifiedAuthentication(
            credential_id=verified.credential_id,
            new_sign_count=verified.new_sign_count,
        )


@dataclass(frozen=True, slots=True)
class _Pending:
    kind: str
    principal_id: str
    display_name: str
    challenge: bytes
    expires_at: datetime


class WebAuthnService:
    ADMIN_ROLE_ID = "admin"
    ADMIN_PERMISSION = "workshop.admin"

    def __init__(
        self,
        *,
        principals: PrincipalService,
        sessions: SessionStore,
        state_path: Path,
        rp_id: str,
        origin: str,
        rp_name: str,
        backend: WebAuthnBackend | None = None,
        clock: Callable[[], datetime] | None = None,
        challenge_ttl: timedelta = timedelta(minutes=5),
    ):
        if challenge_ttl <= timedelta(0):
            raise ValueError("challenge TTL must be positive")
        self.principals = principals
        self.sessions = sessions
        self.state_path = Path(state_path)
        self.rp_id = rp_id
        self.origin = origin
        self.rp_name = rp_name
        self.backend = backend or PyWebAuthnBackend(
            rp_id=rp_id,
            origin=origin,
            rp_name=rp_name,
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.challenge_ttl = challenge_ttl
        self._lock = threading.RLock()
        self._pending: dict[str, _Pending] = {}
        self._credentials: dict[str, list[PasskeyCredential]] = {}
        self._recovery_hashes: dict[str, list[str]] = {}
        self.bootstrap_completed = False
        self._load()

    def begin_admin_bootstrap(
        self,
        principal_id: str,
        *,
        display_name: str,
    ) -> CeremonyStart:
        with self._lock:
            if self.bootstrap_completed or any(
                isinstance(item, UserPrincipal)
                for item in self.principals.list()
            ):
                raise PermissionError("admin bootstrap already completed")
            # Validate identity fields before creating a pending challenge.
            UserPrincipal(
                principal_id=principal_id,
                display_name=display_name,
            )
            return self._begin_registration(
                kind="bootstrap",
                principal_id=principal_id,
                display_name=display_name,
                exclude_credentials=(),
            )

    def begin_login(self, principal_id: str) -> CeremonyStart:
        with self._lock:
            self.principals.get(principal_id)
            credentials = tuple(self._credentials.get(principal_id, ()))
            if not credentials:
                raise PermissionError("principal has no registered passkey")
            challenge = secrets.token_bytes(32)
            challenge_id = secrets.token_urlsafe(24)
            options = self.backend.authentication_options(
                challenge=challenge,
                allow_credentials=tuple(
                    _unb64(item.credential_id_b64)
                    for item in credentials
                ),
            )
            self._pending[challenge_id] = _Pending(
                kind="login",
                principal_id=principal_id,
                display_name="",
                challenge=challenge,
                expires_at=self._now() + self.challenge_ttl,
            )
            return CeremonyStart(
                challenge_id=challenge_id,
                challenge_b64=_b64(challenge),
                options_json=options,
            )

    def finish_admin_bootstrap(
        self,
        challenge_id: str,
        response: dict[str, object],
    ) -> BootstrapResult:
        pending = self._consume(challenge_id, "bootstrap")
        verified = self.backend.verify_registration(
            response,
            expected_challenge=pending.challenge,
        )
        credential = PasskeyCredential(
            principal_id=pending.principal_id,
            credential_id_b64=_b64(verified.credential_id),
            public_key_b64=_b64(verified.public_key),
            sign_count=verified.sign_count,
        )

        with self._lock:
            if self.bootstrap_completed:
                raise PermissionError("admin bootstrap already completed")
            created_principal = False
            granted_role = False
            try:
                self._ensure_admin_role()
                self.principals.create(
                    UserPrincipal(
                        principal_id=pending.principal_id,
                        display_name=pending.display_name,
                    )
                )
                created_principal = True
                self.principals.grant_global_role(
                    pending.principal_id,
                    self.ADMIN_ROLE_ID,
                )
                granted_role = True

                recovery_codes = tuple(
                    secrets.token_urlsafe(10)
                    for _ in range(8)
                )
                previous_credentials = self._credentials.get(
                    pending.principal_id
                )
                previous_recovery = self._recovery_hashes.get(
                    pending.principal_id
                )
                self._credentials[pending.principal_id] = [credential]
                self._recovery_hashes[pending.principal_id] = [
                    self._recovery_digest(code)
                    for code in recovery_codes
                ]
                self.bootstrap_completed = True
                try:
                    self._persist()
                except Exception:
                    self.bootstrap_completed = False
                    if previous_credentials is None:
                        self._credentials.pop(pending.principal_id, None)
                    else:
                        self._credentials[pending.principal_id] = previous_credentials
                    if previous_recovery is None:
                        self._recovery_hashes.pop(pending.principal_id, None)
                    else:
                        self._recovery_hashes[pending.principal_id] = previous_recovery
                    raise
            except Exception:
                if granted_role:
                    self.principals.revoke_global_role(
                        pending.principal_id,
                        self.ADMIN_ROLE_ID,
                    )
                if created_principal:
                    self.principals.remove_unreferenced(
                        pending.principal_id
                    )
                raise

        session = self.sessions.issue(pending.principal_id)
        return BootstrapResult(
            session=session,
            recovery_codes=recovery_codes,
        )

    def finish_login(
        self,
        challenge_id: str,
        response: dict[str, object],
    ) -> SessionToken:
        pending = self._consume(challenge_id, "login")
        credential_id = self.backend.credential_id_from_response(response)
        target_b64 = _b64(credential_id)

        with self._lock:
            credentials = self._credentials.get(pending.principal_id, [])
            index = next(
                (
                    idx
                    for idx, item in enumerate(credentials)
                    if secrets.compare_digest(
                        item.credential_id_b64,
                        target_b64,
                    )
                ),
                None,
            )
            if index is None:
                raise PermissionError("unknown passkey credential")
            current = credentials[index]

        verified = self.backend.verify_authentication(
            response,
            expected_challenge=pending.challenge,
            credential_public_key=_unb64(current.public_key_b64),
            credential_current_sign_count=current.sign_count,
        )
        if not secrets.compare_digest(
            _b64(verified.credential_id),
            current.credential_id_b64,
        ):
            raise PermissionError("verified passkey credential mismatch")

        updated = current.model_copy(
            update={"sign_count": verified.new_sign_count}
        )
        with self._lock:
            previous = self._credentials[pending.principal_id][index]
            self._credentials[pending.principal_id][index] = updated
            try:
                self._persist()
            except Exception:
                self._credentials[pending.principal_id][index] = previous
                raise
        return self.sessions.issue(pending.principal_id)

    def authenticate_recovery_code(
        self,
        principal_id: str,
        code: str,
    ) -> SessionToken:
        self.principals.get(principal_id)
        digest = self._recovery_digest(code)
        with self._lock:
            hashes = self._recovery_hashes.get(principal_id, [])
            index = next(
                (
                    idx
                    for idx, value in enumerate(hashes)
                    if secrets.compare_digest(value, digest)
                ),
                None,
            )
            if index is None:
                raise PermissionError("invalid recovery code")
            removed = hashes.pop(index)
            try:
                self._persist()
            except Exception:
                hashes.insert(index, removed)
                raise
        try:
            return self.sessions.issue(principal_id)
        except Exception:
            with self._lock:
                hashes = self._recovery_hashes.setdefault(
                    principal_id,
                    [],
                )
                hashes.insert(index, removed)
                self._persist()
            raise

    def credentials_for(
        self,
        principal_id: str,
    ) -> tuple[PasskeyCredential, ...]:
        with self._lock:
            return tuple(self._credentials.get(principal_id, ()))

    def _begin_registration(
        self,
        *,
        kind: str,
        principal_id: str,
        display_name: str,
        exclude_credentials: tuple[bytes, ...],
    ) -> CeremonyStart:
        challenge = secrets.token_bytes(32)
        challenge_id = secrets.token_urlsafe(24)
        user_handle = secrets.token_bytes(32)
        options = self.backend.registration_options(
            user_id=user_handle,
            username=principal_id,
            display_name=display_name,
            challenge=challenge,
            exclude_credentials=exclude_credentials,
        )
        self._pending[challenge_id] = _Pending(
            kind=kind,
            principal_id=principal_id,
            display_name=display_name,
            challenge=challenge,
            expires_at=self._now() + self.challenge_ttl,
        )
        return CeremonyStart(
            challenge_id=challenge_id,
            challenge_b64=_b64(challenge),
            options_json=options,
        )

    def _consume(self, challenge_id: str, expected_kind: str) -> _Pending:
        with self._lock:
            pending = self._pending.pop(challenge_id, None)
        if pending is None:
            raise PermissionError("invalid or already used challenge")
        if pending.kind != expected_kind:
            raise PermissionError("challenge ceremony mismatch")
        if pending.expires_at <= self._now():
            raise PermissionError("challenge expired")
        return pending

    def _ensure_admin_role(self) -> None:
        try:
            role = self.principals.get_role(self.ADMIN_ROLE_ID)
        except KeyError:
            self.principals.create_role(
                RoleDefinition(
                    role_id=self.ADMIN_ROLE_ID,
                    allow=(self.ADMIN_PERMISSION,),
                )
            )
            return
        if (
            self.ADMIN_PERMISSION not in role.allow
            or self.ADMIN_PERMISSION in role.deny
        ):
            raise ValueError("existing admin role is incompatible")

    @staticmethod
    def _recovery_digest(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WebAuthn clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported authentication state version")
        self.bootstrap_completed = bool(
            payload.get("bootstrap_completed", False)
        )
        for raw in payload.get("credentials", []):
            credential = PasskeyCredential.model_validate(raw)
            self.principals.get(credential.principal_id)
            self._credentials.setdefault(
                credential.principal_id,
                [],
            ).append(credential)
        raw_recovery = payload.get("recovery_hashes", {})
        if not isinstance(raw_recovery, dict):
            raise ValueError("recovery hashes must be an object")
        self._recovery_hashes = {
            str(principal_id): [str(value) for value in values]
            for principal_id, values in raw_recovery.items()
        }

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "bootstrap_completed": self.bootstrap_completed,
            "credentials": [
                credential.model_dump(mode="json")
                for principal_id in sorted(self._credentials)
                for credential in self._credentials[principal_id]
            ],
            "recovery_hashes": {
                principal_id: list(values)
                for principal_id, values in sorted(
                    self._recovery_hashes.items()
                )
            },
        }
        temporary = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
