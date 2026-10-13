"""Fixed, opt-in REA registration for the single-operator Server Mode gateway."""
from __future__ import annotations

import threading
import time

from ai_workshop.mcp_runtime.discovery import McpDiscoveryService
from ai_workshop.mcp_runtime.models import McpRegistration, McpRegistrationScope, McpServerState, McpTransportKind
from ai_workshop.mcp_runtime.proxy import McpProxyService
from ai_workshop.mcp_runtime.registry import McpRegistryStore
from ai_workshop.rea.client import ReaMcpClient


class ServerOperator:
    """Identity of the existing private gateway, not an end-user auth mechanism."""
    def current_principal_id(self): return 'server-operator'


class ReaProxy(McpProxyService):
    def __init__(self, registry, client):
        self._client = client
        self._lock = threading.RLock()
        self._refreshed = 0.0
        super().__init__(registry, self)

    def client_for(self, server_id):
        if server_id != 'rea':
            raise KeyError('unknown REA server')
        return self._client

    def _refresh(self, server_id):
        self.client_for(server_id)
        with self._lock:
            if self.registry.get(server_id).registration.state is McpServerState.RUNNING and time.monotonic() - self._refreshed < 30:
                return
            try:
                McpDiscoveryService(self.registry, self).refresh(server_id)
                self.registry.set_state(server_id, McpServerState.RUNNING)
                self._refreshed = time.monotonic()
            except Exception:
                self.registry.set_state(server_id, McpServerState.FAILED)
                raise RuntimeError('REA_UNAVAILABLE: check rea-mcp health') from None

    def servers_list(self, principal_id):
        try:
            self._refresh('rea')
        except RuntimeError:
            pass
        return super().servers_list(principal_id)

    def server_get(self, principal_id, server_id):
        self._refresh(server_id)
        return super().server_get(principal_id, server_id)

    def tools_list(self, principal_id, server_id):
        self._refresh(server_id)
        return super().tools_list(principal_id, server_id)

    def resources_list(self, principal_id, server_id):
        self._refresh(server_id)
        return super().resources_list(principal_id, server_id)

    def prompts_list(self, principal_id, server_id):
        self._refresh(server_id)
        return super().prompts_list(principal_id, server_id)

    def _running(self, server_id):
        self._refresh(server_id)
        return super()._running(server_id)


def build_rea_proxy(url, token, state_root):
    # Deployment selects one private sidecar, never an arbitrary caller URL.
    if url != 'http://rea-mcp:8796/mcp':
        raise ValueError('REA URL must be http://rea-mcp:8796/mcp')
    registry = McpRegistryStore(state_root / 'rea-mcp.json')
    if not registry.list():
        registry.register(McpRegistration(server_id='rea', display_name='REA', transport=McpTransportKind.HTTP,
            scope=McpRegistrationScope.GLOBAL, scope_id='global', owner_principal_id='server-operator'))
    if [r.registration.server_id for r in registry.list()] != ['rea']:
        raise ValueError('REA registry contains unexpected registrations')
    registry.set_state('rea', McpServerState.STOPPED)
    return ReaProxy(registry, ReaMcpClient(url, token=token, uds='/run/rea/mcp.sock'))
