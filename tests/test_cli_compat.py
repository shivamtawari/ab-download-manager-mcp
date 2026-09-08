"""Unit tests for CliBackend execution, Python 3.10 timeout compatibility, and version parsing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from abdm_mcp.backends.cli import CliBackend
from abdm_mcp.config import Settings
from abdm_mcp.errors import (
    CLIOutputLimitError,
    CLITimeoutError,
    CLIUnavailableError,
)


@pytest.fixture
def cli_settings(tmp_path):
    fake_cli = tmp_path / "ABDownloadManagerCli.exe"
    fake_cli.write_text("fake binary")
    return Settings(
        config_dir=tmp_path,
        allowed_roots=[tmp_path],
        cli_path=fake_cli,
        cli_timeout=0.1,
        cli_max_output_bytes=100,
    )


async def test_get_version_parsing(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    async def mock_execute(args):
        return 0, "ABDownloadManagerCli version 1.10.2\nExtra info", ""

    monkeypatch.setattr(cli, "_execute_bounded", mock_execute)
    version = await cli.get_version()
    assert version == "1.10.2"


async def test_get_version_unavailable(tmp_path):
    settings = Settings(
        config_dir=tmp_path,
        allowed_roots=[tmp_path],
        cli_path=tmp_path / "nonexistent.exe",
    )
    cli = CliBackend(settings)
    assert await cli.get_version() is None


async def test_execute_bounded_timeout_python310_compat(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    # Mock a subprocess that sleeps longer than timeout
    async def mock_create_subprocess_exec(*args, **kwargs):
        proc = MagicMock()
        proc.stdout = asyncio.StreamReader()
        proc.stderr = asyncio.StreamReader()
        proc.kill = MagicMock()

        async def fake_wait():
            await asyncio.sleep(1.0)
            return 0

        proc.wait = fake_wait
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    with pytest.raises(CLITimeoutError, match="timed out"):
        await cli._execute_bounded(["test"])


async def test_execute_bounded_output_limit(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    # Mock a subprocess that emits more bytes than cli_max_output_bytes (100)
    async def mock_create_subprocess_exec(*args, **kwargs):
        proc = MagicMock()
        reader = asyncio.StreamReader()
        reader.feed_data(b"x" * 200)
        reader.feed_eof()

        err_reader = asyncio.StreamReader()
        err_reader.feed_eof()

        proc.stdout = reader
        proc.stderr = err_reader
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=0)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    with pytest.raises(CLIOutputLimitError, match="exceeded 100 bytes buffer limit"):
        await cli._execute_bounded(["test"])


async def test_execute_bounded_missing_pipes(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    async def mock_create_subprocess_exec(*args, **kwargs):
        proc = MagicMock()
        proc.stdout = None
        proc.stderr = None
        proc.kill = MagicMock()
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    with pytest.raises(CLIUnavailableError, match="failed to establish stdout/stderr pipes"):
        await cli._execute_bounded(["test"])


async def test_start_if_not_started(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    called_args = []

    async def mock_execute(args):
        called_args.append(args)
        return 0, "App already running or started", ""

    monkeypatch.setattr(cli, "_execute_bounded", mock_execute)
    assert await cli.start_if_not_started() is True
    assert called_args == [["gui", "start-if-not-started"]]


async def test_get_integration_port(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    async def mock_execute(args):
        return 0, "\x1b[32m15151\x1b[0m\n", ""

    monkeypatch.setattr(cli, "_execute_bounded", mock_execute)
    port = await cli.get_integration_port()
    assert port == 15151


async def test_show_downloads_resilient_ansi_parsing(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    # Simulated Mordant table output with ANSI escape sequences and unicode borders
    mock_table = (
        "\x1b[1m┌─────┬───────────────────────────┬───────────────────────────┬───────────────────────────────┐\x1b[0m\n"
        "│ ID  │ Status                    │ Name                      │ Folder                        │\n"
        "├─────┼───────────────────────────┼───────────────────────────┼───────────────────────────────┤\n"
        "│ 18  │ \x1b[33mPaused\x1b[0m                    │ test_model.bin            │ C:\\Downloads\\ABDM             │\n"
        "│ 19  │ \x1b[32mDownloading\x1b[0m               │ weights.safetensors       │ C:\\Downloads\\ABDM             │\n"
        "└─────┴───────────────────────────┴───────────────────────────┴───────────────────────────────┘\n"
    )

    async def mock_execute(args):
        return 0, mock_table, ""

    monkeypatch.setattr(cli, "_execute_bounded", mock_execute)
    items = await cli.show_downloads()
    assert len(items) == 2
    assert items[0].id == "18"
    assert items[0].status == "Paused"
    assert items[0].name == "test_model.bin"
    assert items[0].folder == "C:\\Downloads\\ABDM"

    assert items[1].id == "19"
    assert items[1].status == "Downloading"
    assert items[1].name == "weights.safetensors"


async def test_show_downloads_multi_id(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    called_args = []

    async def mock_execute(args):
        called_args.append(args)
        return 0, "│ 18 │ Paused │ file.zip │ C:\\Folder │\n", ""

    monkeypatch.setattr(cli, "_execute_bounded", mock_execute)
    items = await cli.show_downloads(download_ids=["18", "19"])
    assert called_args[0] == ["download", "show", "18", "19"]
    assert len(items) == 1
    assert items[0].id == "18"


async def test_pause_resume_remove_multi_id(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    calls = []

    async def mock_execute(args):
        calls.append(args)
        return 0, "OK", ""

    monkeypatch.setattr(cli, "_execute_bounded", mock_execute)
    await cli.pause_download(["1", "2"])
    await cli.resume_download(["1", "2"])
    await cli.remove_download(["1", "2"])

    assert calls == [
        ["download", "pause", "1", "2"],
        ["download", "resume", "1", "2"],
        ["download", "remove", "1", "2"],
    ]


async def test_add_download_hls_and_options(cli_settings, monkeypatch):
    cli = CliBackend(cli_settings)

    called_args = []

    async def mock_execute(args):
        called_args.append(args)
        return 0, "42\n", ""

    monkeypatch.setattr(cli, "_execute_bounded", mock_execute)
    d_id = await cli.add_download(
        url="https://example.com/stream.m3u8",
        filename="stream.mp4",
        folder="C:\\Downloads",
        queue_id=1,
        category_id=5,
        download_page="https://example.com/watch",
        start=True,
        start_queue=True,
        protocol="hls",
    )
    assert d_id == "42"
    expected_args = [
        "download",
        "add",
        "hls",
        "--link",
        "https://example.com/stream.m3u8",
        "--name",
        "stream.mp4",
        "--folder",
        "C:\\Downloads",
        "--queue",
        "1",
        "--category",
        "5",
        "--download-page",
        "https://example.com/watch",
        "--start",
        "--start-queue",
    ]
    assert called_args[0] == expected_args

