from __future__ import annotations

import httpx
import pytest

from ai_workshop.forge.http import ForgeHttpClient, ForgeHttpError


def client_for(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return ForgeHttpClient(
        base_url="https://forge.example/api",
        default_headers={"Authorization": "Bearer super-secret-token"},
        client=http,
        **kwargs,
    )


def test_provider_list_follows_pagination():
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        page = request.url.params.get("page", "1")
        if page == "1":
            return httpx.Response(
                200,
                json=[{"id": 1}, {"id": 2}],
                headers={
                    "Link": (
                        '<https://forge.example/api/repos?page=2>; rel="next"'
                    )
                },
            )
        return httpx.Response(200, json=[{"id": 3}])

    forge = client_for(handler)

    items = forge.get_paginated("/repos")

    assert items == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert len(calls) == 2


def test_gitlab_style_next_page_header_is_followed():
    def handler(request: httpx.Request):
        page = request.url.params.get("page", "1")
        if page == "1":
            return httpx.Response(
                200,
                json=[{"id": 1}],
                headers={"X-Next-Page": "2"},
            )
        return httpx.Response(200, json=[{"id": 2}], headers={"X-Next-Page": ""})

    forge = client_for(handler)

    assert forge.get_paginated("/repos") == [{"id": 1}, {"id": 2}]


def test_pagination_is_bounded_even_if_provider_loops():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json=[{"id": calls}],
            headers={
                "Link": (
                    '<https://forge.example/api/repos?page=1>; rel="next"'
                )
            },
        )

    forge = client_for(handler, max_pages=3)

    with pytest.raises(ForgeHttpError, match="pagination limit"):
        forge.get_paginated("/repos")

    assert calls == 3


def test_retryable_get_is_retried_only_up_to_bound():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="provider unavailable")

    forge = client_for(handler, max_retries=2)

    with pytest.raises(ForgeHttpError) as caught:
        forge.get_json("/repos/one")

    assert calls == 3
    assert caught.value.retryable is True


def test_mutating_request_is_not_automatically_retried():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="provider unavailable")

    forge = client_for(handler, max_retries=5)

    with pytest.raises(ForgeHttpError):
        forge.post_json("/repos", {"name": "demo"})

    assert calls == 1


def test_provider_error_is_normalized_and_redacted():
    secret_body = "internal stack with super-secret-token"

    def handler(request: httpx.Request):
        return httpx.Response(
            500,
            text=secret_body,
            headers={"X-Debug": "private"},
        )

    forge = client_for(handler, max_retries=0)

    with pytest.raises(ForgeHttpError) as caught:
        forge.get_json("/repos/one")

    rendered = str(caught.value)
    assert "super-secret-token" not in rendered
    assert "internal stack" not in rendered
    assert "X-Debug" not in rendered
    assert caught.value.status_code == 500
    assert caught.value.code == "FORGE_PROVIDER_ERROR"


def test_timeout_is_normalized_without_transport_details():
    def handler(request: httpx.Request):
        raise httpx.ReadTimeout("socket details with secret", request=request)

    forge = client_for(handler, max_retries=0)

    with pytest.raises(ForgeHttpError) as caught:
        forge.get_json("/repos/one")

    assert caught.value.code == "FORGE_TIMEOUT"
    assert "socket details" not in str(caught.value)


def test_invalid_json_is_normalized():
    def handler(request: httpx.Request):
        return httpx.Response(200, content=b"not-json")

    forge = client_for(handler)

    with pytest.raises(ForgeHttpError) as caught:
        forge.get_json("/repos/one")

    assert caught.value.code == "FORGE_RESPONSE_INVALID"


def test_redirect_is_not_followed_with_authorization_header():
    def handler(request: httpx.Request):
        return httpx.Response(
            302,
            headers={"Location": "https://evil.example/capture"},
        )

    forge = client_for(handler)

    with pytest.raises(ForgeHttpError) as caught:
        forge.get_json("/repos/one")

    assert caught.value.status_code == 302
