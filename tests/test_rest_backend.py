"""Unit tests for REST backend using respx."""

import pytest
import respx

from abdm_mcp.backends.rest import RestBackend
from abdm_mcp.config import Settings
from abdm_mcp.errors import ABDMAuthenticationError


@pytest.fixture
def settings(tmp_path):
    return Settings(
        config_dir=tmp_path,
        port=15151,
        api_key="test-key",
        allowed_roots=[tmp_path],
    )


@respx.mock
async def test_get_queues_success(settings):
    respx.get("http://127.0.0.1:15151/queues").respond(
        200, json=[{"id": 0, "name": "Main"}, {"id": 1, "name": "Videos"}]
    )
    backend = RestBackend(settings)
    queues = await backend.get_queues()
    assert len(queues) == 2
    assert queues[0].name == "Main"
    assert queues[1].id == 1


@respx.mock
async def test_get_queues_auth_failure(settings):
    respx.get("http://127.0.0.1:15151/queues").respond(401)
    backend = RestBackend(settings)
    with pytest.raises(ABDMAuthenticationError):
        await backend.get_queues()


@respx.mock
async def test_add_interactive(settings):
    respx.post("http://127.0.0.1:15151/add").respond(200)
    backend = RestBackend(settings)
    ok = await backend.add_interactive("https://example.com/file.zip")
    assert ok is True


@respx.mock
async def test_add_headless(settings):
    respx.post("http://127.0.0.1:15151/start-headless-download").respond(200)
    backend = RestBackend(settings)
    ok = await backend.add_headless(
        url="https://example.com/file.zip",
        filename="file.zip",
        folder="/tmp/downloads",
        queue_id=0,
    )
    assert ok is True
