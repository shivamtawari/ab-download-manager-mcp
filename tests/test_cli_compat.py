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
