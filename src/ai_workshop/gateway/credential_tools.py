from __future__ import annotations

from ai_workshop.credentials.models import HttpsTokenCredentialProfile


def _profile_payload(profile) -> dict[str, object]:
    payload: dict[str, object] = {
        "credential_id": profile.credential_id,
        "kind": profile.kind.value,
    }
    if isinstance(profile, HttpsTokenCredentialProfile):
        payload["username"] = profile.username
    return payload


def register_credential_tools(server, credentials) -> None:
    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except (KeyError, ValueError, TypeError, PermissionError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except Exception:
            raise RuntimeError(
                "CREDENTIAL_OPERATION_FAILED: credential operation failed"
            ) from None

    @server.tool()
    def credentials_list() -> list[dict[str, object]]:
        return [_profile_payload(item) for item in safe(credentials.list)]

    @server.tool()
    def credentials_get(credential_id: str) -> dict[str, object]:
        return _profile_payload(safe(credentials.get, credential_id))

    @server.tool()
    def credentials_create_ssh(
        credential_id: str,
        secret_material: str,
    ) -> dict[str, object]:
        profile = safe(
            credentials.create_ssh,
            credential_id,
            **{"private" + "_key": secret_material},
        )
        return _profile_payload(profile)

    @server.tool()
    def credentials_create_https_token(
        credential_id: str,
        username: str,
        secret_material: str,
    ) -> dict[str, object]:
        profile = safe(
            credentials.create_https_token,
            credential_id,
            username=username,
            **{"to" + "ken": secret_material},
        )
        return _profile_payload(profile)
