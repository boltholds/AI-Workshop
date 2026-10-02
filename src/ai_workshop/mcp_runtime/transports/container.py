from __future__ import annotations

from ai_workshop.server.models import (
    RuntimeOutboundAccess,
    RuntimeWorkloadKind,
    RuntimeWorkloadSpec,
)


class ContainerMcpTransport:
    def __init__(
        self,
        runtime,
        *,
        image_for,
        command_for,
        port_for,
        client_factory,
        allow_internet: bool = False,
    ):
        self.runtime = runtime
        self.image_for = image_for
        self.command_for = command_for
        self.port_for = port_for
        self.client_factory = client_factory
        self.allow_internet = allow_internet
        self._handles: dict[str, object] = {}

    def start(self, registration):
        port = self.port_for(registration)
        image = self.image_for(registration)
        self.runtime.ensure_image(image)
        spec = RuntimeWorkloadSpec(
            workload_id=registration.server_id,
            image=image,
            command=tuple(self.command_for(registration)),
            kind=RuntimeWorkloadKind.MCP,
            outbound=(
                RuntimeOutboundAccess.INTERNET
                if self.allow_internet
                else RuntimeOutboundAccess.NONE
            ),
            container_ports=(port,),
        )
        self.runtime.create(spec)
        try:
            self.runtime.start(registration.server_id)
            endpoint = self.runtime.publish_private_endpoint(
                registration.server_id,
                port,
            )
            handle = self.client_factory(endpoint)
            self._handles[registration.server_id] = handle
            return handle
        except Exception:
            try:
                self.runtime.remove(registration.server_id)
            except Exception:
                pass
            raise

    def stop(self, server_id: str) -> None:
        handle = self._handles.pop(server_id, None)
        if handle is not None and hasattr(handle, "close"):
            handle.close()
        try:
            self.runtime.stop(server_id)
        finally:
            self.runtime.remove(server_id)
