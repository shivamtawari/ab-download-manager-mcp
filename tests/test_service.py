"""Unit tests for ABDMService orchestration and validation."""

import pytest
import respx

from abdm_mcp.config import Settings
from abdm_mcp.errors import ABDMError, UnsupportedParameterError
from abdm_mcp.service import ABDMService


@pytest.fixture
def settings(tmp_path):
    return Settings(
        config_dir=tmp_path,
        port=15151,
        allowed_roots=[tmp_path],
        allow_file_deletion=False,
    )


@respx.mock
async def test_interactive_mode_disparity_rejection(settings):
    service = ABDMService(settings)

    # Reject filename in interactive mode
    with pytest.raises(UnsupportedParameterError, match="cannot be preselected"):
        await service.download("https://example.com/file.zip", mode="interactive", filename="file.zip")

    # Reject subdirectory in interactive mode
    with pytest.raises(UnsupportedParameterError, match="cannot be preselected"):
        await service.download("https://example.com/file.zip", mode="interactive", subdirectory="sub")

    # Reject queue_id in interactive mode
    with pytest.raises(UnsupportedParameterError, match="cannot be preselected"):
        await service.download("https://example.com/file.zip", mode="interactive", queue_id=0)


@respx.mock
async def test_batch_download_limits(settings):
    service = ABDMService(settings)
    urls = [f"https://example.com/file_{i}.zip" for i in range(55)]
    with pytest.raises(ABDMError, match="exceeds maximum allowed batch limit"):
        await service.download_batch(urls)


@respx.mock
async def test_deletion_disabled_by_default(settings):
    service = ABDMService(settings)
    with pytest.raises(ABDMError, match="File deletion is disabled by security policy"):
        await service.remove("123", delete_file=True)


async def test_status_filtering_active_and_completed(settings, monkeypatch):
    from abdm_mcp.models import DownloadInfo

    service = ABDMService(settings)

    mock_downloads = [
        DownloadInfo(id="1", name="active1.bin", status="Downloading", folder="/tmp"),
        DownloadInfo(id="2", name="done1.bin", status="Finished", folder="/tmp"),
        DownloadInfo(id="3", name="paused1.bin", status="Paused", folder="/tmp"),
        DownloadInfo(id="4", name="failed1.bin", status="Error", folder="/tmp"),
    ]

    async def mock_is_available():
        return True

    async def mock_show():
        return mock_downloads

    monkeypatch.setattr(service.cli, "is_available", mock_is_available)
    monkeypatch.setattr(service.cli, "show_downloads", mock_show)

    # status="active" should match "Downloading"
    active_res = await service.list_downloads(status="active")
    assert active_res.count == 1
    assert active_res.items[0].id == "1"

    # status="completed" should match "Finished"
    completed_res = await service.list_downloads(status="completed")
    assert completed_res.count == 1
    assert completed_res.items[0].id == "2"

    # status="paused" should match "Paused"
    paused_res = await service.list_downloads(status="paused")
    assert paused_res.count == 1
    assert paused_res.items[0].id == "3"


async def test_check_status_health_metadata(settings, monkeypatch):
    service = ABDMService(settings)

    # 1. When REST is unavailable but CLI is available
    async def mock_rest_health_down():
        return False, None, "connection refused"

    async def mock_cli_ok():
        return True

    async def mock_cli_ver():
        return "1.10.2"

    monkeypatch.setattr(service.rest, "check_health", mock_rest_health_down)
    monkeypatch.setattr(service.cli, "is_available", mock_cli_ok)
    monkeypatch.setattr(service.cli, "get_version", mock_cli_ver)

    report = await service.check_status()
    assert report.rest_available is False
    assert report.cli_available is True
    assert report.cli_version == "1.10.2"
    assert report.shared_state_verified is False  # False because REST was down

    # 2. When both REST and CLI are available
    async def mock_rest_health_up():
        return True, True, None

    monkeypatch.setattr(service.rest, "check_health", mock_rest_health_up)
    report2 = await service.check_status()
    assert report2.rest_available is True
    assert report2.cli_available is True
    assert report2.shared_state_verified is True


@respx.mock
async def test_batch_preserves_actual_failing_backend(settings, monkeypatch):
    import httpx

    service = ABDMService(settings)

    # CLI is unavailable
    async def mock_cli_unavailable():
        return False

    monkeypatch.setattr(service.cli, "is_available", mock_cli_unavailable)

    # REST headless fails with connection error
    async def mock_rest_add_headless(**kwargs):
        raise httpx.ConnectError("REST integration server unreachable")

    monkeypatch.setattr(service.rest, "add_headless", mock_rest_add_headless)

    res = await service.download_batch(["https://example.com/file.zip"], mode="headless")
    assert res.submitted == 0
    assert res.failed == 1
    # Crucial assertion: backend must report "rest" because REST was the backend that attempted and failed
    assert res.items[0].backend == "rest"
    assert "unreachable" in res.items[0].message
