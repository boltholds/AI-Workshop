from __future__ import annotations

import httpx


class AnalysisClient:
    """Transport-only gateway proxy. Secrets never reach tool responses."""

    def __init__(self, base_url: str, *, token: str):
        if not token:
            raise ValueError('analysis token required')
        self._http = httpx.Client(
            base_url=base_url.rstrip('/'),
            headers={'Authorization': f'Bearer {token}'},
            timeout=910,
        )

    def _call(self, method: str, path: str, **kwargs) -> dict[str, object]:
        try:
            response = self._http.request(method, path, **kwargs)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError('invalid worker result')
            return result
        except (httpx.HTTPError, ValueError):
            # Avoid forwarding response body, internal URL or private configuration.
            raise RuntimeError('ANALYSIS_WORKER_UNAVAILABLE: operation failed') from None

    def shell_exec(self, project_id: str, argv: list[str], timeout_seconds: float):
        return self._call('POST', '/v1/shell/exec', json={
            'project_id': project_id, 'argv': argv, 'timeout_seconds': timeout_seconds,
        })

    def cargo_test(self, project_id: str, manifest_path: str, timeout_seconds: float):
        return self._call('POST', '/v1/cargo/test', json={
            'project_id': project_id, 'manifest_path': manifest_path,
            'timeout_seconds': timeout_seconds,
        })

    def binary_analyze(self, project_id: str, path: str):
        return self._call('POST', '/v1/binary/analyze', json={
            'project_id': project_id, 'path': path,
        })

    def analysis_get_results(self, project_id: str, analysis_id: str):
        return self._call('GET', f'/v1/binary/results/{project_id}/{analysis_id}')
