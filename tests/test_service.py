from unittest.mock import AsyncMock

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

    monkeypatch.setattr(service, "ensure_app_ready", AsyncMock(return_value=True))
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

    monkeypatch.setattr(service, "ensure_app_ready", AsyncMock(return_value=True))
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
    monkeypatch.setattr(service, "ensure_app_ready", AsyncMock(return_value=True))

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


async def test_ensure_app_ready_already_online(settings, monkeypatch):
    service = ABDMService(settings)

    monkeypatch.setattr(service.rest, "is_available", AsyncMock(return_value=True))
    cli_wake = AsyncMock()
    monkeypatch.setattr(service.cli, "start_if_not_started", cli_wake)

    ready = await service.ensure_app_ready()
    assert ready is True
    cli_wake.assert_not_called()


async def test_ensure_app_ready_port_discovery(settings, monkeypatch):
    service = ABDMService(settings)

    # Initially port 15151 unavailable, but port 19999 available
    async def mock_is_available():
        return service.rest.port == 19999

    monkeypatch.setattr(service.rest, "is_available", mock_is_available)
    monkeypatch.setattr(service.cli, "is_available", AsyncMock(return_value=True))
    monkeypatch.setattr(service.cli, "get_integration_port", AsyncMock(return_value=19999))

    ready = await service.ensure_app_ready()
    assert ready is True
    assert service.rest.port == 19999
    assert service.rest.base_url == "http://127.0.0.1:19999"


async def test_ensure_app_ready_auto_wake(settings, monkeypatch):
    service = ABDMService(settings)

    call_count = 0

    async def mock_is_available():
        nonlocal call_count
        call_count += 1
        return call_count > 1  # becomes available after wake

    monkeypatch.setattr(service.rest, "is_available", mock_is_available)
    monkeypatch.setattr(service.cli, "is_available", AsyncMock(return_value=True))
    monkeypatch.setattr(service.cli, "get_integration_port", AsyncMock(return_value=None))
    wake_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(service.cli, "start_if_not_started", wake_mock)

    ready = await service.ensure_app_ready()
    assert ready is True
    wake_mock.assert_called_once()


async def test_pause_all_and_resume_all(settings, monkeypatch):
    from abdm_mcp.models import DownloadInfo, DownloadListResult

    service = ABDMService(settings)
    monkeypatch.setattr(service, "ensure_app_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(service.cli, "is_available", AsyncMock(return_value=True))

    mock_pause = AsyncMock()
    mock_resume = AsyncMock()
    monkeypatch.setattr(service.cli, "pause_download", mock_pause)
    monkeypatch.setattr(service.cli, "resume_download", mock_resume)

    # 1. When downloads exist
    async def mock_list(status=None):
        if status == "active":
            return DownloadListResult(
                items=[DownloadInfo(id="1", name="a.bin", status="Downloading", folder="/tmp")],
                count=1,
            )
        elif status == "paused":
            return DownloadListResult(
                items=[DownloadInfo(id="2", name="b.bin", status="Paused", folder="/tmp")],
                count=1,
            )
        return DownloadListResult(items=[], count=0)

    monkeypatch.setattr(service, "list_downloads", mock_list)

    pause_res = await service.pause_all()
    assert pause_res.action == "pause_all"
    assert pause_res.count == 1
    assert pause_res.download_ids == ["1"]
    mock_pause.assert_called_once_with(["1"])

    resume_res = await service.resume_all()
    assert resume_res.action == "resume_all"
    assert resume_res.count == 1
    assert resume_res.download_ids == ["2"]
    mock_resume.assert_called_once_with(["2"])

    # 2. When empty
    async def mock_empty_list(status=None):
        return DownloadListResult(items=[], count=0)

    monkeypatch.setattr(service, "list_downloads", mock_empty_list)
    empty_pause = await service.pause_all()
    assert empty_pause.count == 0
    assert "No active downloads" in empty_pause.message


async def test_download_hls(settings, monkeypatch):
    service = ABDMService(settings)
    monkeypatch.setattr(service, "ensure_app_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(service.cli, "is_available", AsyncMock(return_value=True))

    mock_add = AsyncMock(return_value="99")
    monkeypatch.setattr(service.cli, "add_download", mock_add)

    sub = await service.download(
        url="https://example.com/stream.m3u8",
        mode="headless",
        protocol="hls",
        start_queue=True,
    )
    assert sub.accepted is True
    assert sub.download_id == "99"
    assert sub.protocol == "hls"
    assert "HLS" in sub.message
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["protocol"] == "hls"
    assert mock_add.call_args.kwargs["start_queue"] is True


async def test_interactive_mode_throttling_rejection(settings):
    service = ABDMService(settings)

    with pytest.raises(UnsupportedParameterError, match="speed_limit_bytes"):
        await service.download(
            "https://example.com/file.zip",
            mode="interactive",
            speed_limit_bytes=1024,
        )

    with pytest.raises(UnsupportedParameterError, match="category_id"):
        await service.download(
            "https://example.com/file.zip",
            mode="interactive",
            category_id=3,
        )


