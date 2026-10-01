from __future__ import annotations

from ai_workshop.controller.runner import ComposeController, ControllerError


def register_service_tools(server, controller: ComposeController) -> None:
    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except ControllerError as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from None
        except (KeyError, ValueError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None

    @server.tool()
    def services_list() -> list[str]:
        return controller.list_services()

    @server.tool()
    def services_status(service_id: str) -> dict[str, str]:
        status = safe(controller.status, service_id)
        return {"service_id": status.service_id, "stdout": status.stdout}

    @server.tool()
    def services_logs(service_id: str, tail: int = 200) -> str:
        return safe(controller.logs, service_id, tail=tail)

    @server.tool()
    def services_restart(service_id: str) -> dict[str, bool]:
        safe(controller.restart, service_id)
        return {"ok": True}

    @server.tool()
    def services_rebuild(service_id: str) -> dict[str, bool]:
        safe(controller.rebuild, service_id)
        return {"ok": True}

    @server.tool()
    def services_up(service_id: str) -> dict[str, bool]:
        safe(controller.up, service_id)
        return {"ok": True}
