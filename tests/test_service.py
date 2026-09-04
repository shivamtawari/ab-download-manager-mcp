"""Unit tests for ABDMService orchestration and validation."""

import pytest
import respx
from pathlib import Path
from abdm_mcp.config import Settings
from abdm_mcp.errors import ABDMError, UnsupportedParameterError, UnsafeURLError
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
