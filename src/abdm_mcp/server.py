"""Official Model Context Protocol (MCP) server implementation for AB Download Manager."""

from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from abdm_mcp.config import load_settings
from abdm_mcp.models import (
    ActionResult,
    BatchSubmission,
    DownloadInfo,
    DownloadListResult,
    DownloadSubmission,
    HealthReport,
    QueueInfo,
)
from abdm_mcp.service import ABDMService

# Explicit MCP Tool Annotations
DOWNLOAD_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

PAUSE_RESUME_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

REMOVE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

READ_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def create_server() -> FastMCP:
    """Instantiate and configure the FastMCP server with registered ABDM tools."""
    mcp = FastMCP("AB Download Manager")
    settings = load_settings()
    service = ABDMService(settings)

    @mcp.tool(
        name="abdm_download",
        description=(
            "Submit a download task to AB Download Manager with multi-threaded acceleration. "
            "In 'interactive' mode (default), triggers the desktop confirmation GUI. "
            "In 'headless' mode, starts silent background download into allowed sandboxed folder."
        ),
        annotations=DOWNLOAD_ANNOTATIONS,
    )
    async def abdm_download(
        url: str,
        mode: Literal["interactive", "headless"] = "interactive",
        filename: str | None = None,
        subdirectory: str | None = None,
        queue_id: int | None = None,
        headers: dict[str, str] | None = None,
        download_page: str | None = None,
    ) -> DownloadSubmission:
        return await service.download(
            url=url,
            mode=mode,
            filename=filename,
            subdirectory=subdirectory,
            queue_id=queue_id,
            headers=headers,
            download_page=download_page,
        )

    @mcp.tool(
        name="abdm_download_batch",
        description="Enqueue up to 50 URLs in a batch with per-item status tracking.",
        annotations=DOWNLOAD_ANNOTATIONS,
    )
    async def abdm_download_batch(
        urls: list[str],
        mode: Literal["interactive", "headless"] = "interactive",
        queue_id: int | None = None,
    ) -> BatchSubmission:
        return await service.download_batch(
            urls=urls,
            mode=mode,
            queue_id=queue_id,
        )

    @mcp.tool(
        name="abdm_get_queues",
        description="List all configured download queues in AB Download Manager.",
        annotations=READ_ANNOTATIONS,
    )
    async def abdm_get_queues() -> list[QueueInfo]:
        return await service.get_queues()

    @mcp.tool(
        name="abdm_check_status",
        description="Inspect reachability, authentication, port discovery, and capabilities.",
        annotations=READ_ANNOTATIONS,
    )
    async def abdm_check_status() -> HealthReport:
        return await service.check_status()

    @mcp.tool(
        name="abdm_list_downloads",
        description="List downloads currently tracked by AB Download Manager.",
        annotations=READ_ANNOTATIONS,
    )
    async def abdm_list_downloads(
        status: Literal["active", "paused", "completed", "error", "all"] | None = None,
    ) -> DownloadListResult:
        query_status = None if status == "all" else status
        return await service.list_downloads(status=query_status)

    @mcp.tool(
        name="abdm_get_download",
        description="Fetch detailed metadata for a single download task by ID.",
        annotations=READ_ANNOTATIONS,
    )
    async def abdm_get_download(download_id: str) -> DownloadInfo:
        return await service.get_download(download_id=download_id)

    @mcp.tool(
        name="abdm_pause",
        description="Pause an active download task.",
        annotations=PAUSE_RESUME_ANNOTATIONS,
    )
    async def abdm_pause(download_id: str) -> ActionResult:
        return await service.pause(download_id=download_id)

    @mcp.tool(
        name="abdm_resume",
        description="Resume a paused download task.",
        annotations=PAUSE_RESUME_ANNOTATIONS,
    )
    async def abdm_resume(download_id: str) -> ActionResult:
        return await service.resume(download_id=download_id)

    @mcp.tool(
        name="abdm_remove",
        description=(
            "Remove/cancel a download task. File deletion requires explicit policy "
            "opt-in (ABDM_MCP_ALLOW_FILE_DELETION=true) and path verification."
        ),
        annotations=REMOVE_ANNOTATIONS,
    )
    async def abdm_remove(
        download_id: str,
        delete_file: bool = False,
    ) -> ActionResult:
        return await service.remove(download_id=download_id, delete_file=delete_file)

    return mcp
