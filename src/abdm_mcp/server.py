"""Official Model Context Protocol (MCP) server implementation for AB Download Manager."""

from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from abdm_mcp.config import Settings, load_settings
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

SERVER_INSTRUCTIONS = (
    "Use AB Download Manager to offload large file downloads (model weights, datasets, "
    "disk images, archives, media files, and HLS video streams) instead of downloading them directly through "
    "in-process HTTP calls. Use 'interactive' mode when the user should confirm the download "
    "location via the desktop GUI, or 'headless' mode for silent background downloads into "
    "the sandboxed download folder. Use abdm_download_hls for .m3u8 streams, abdm_pause_all / abdm_resume_all "
    "for mass task control, and check status with abdm_check_status before querying queues."
)


def create_server(
    settings: Settings | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Instantiate and configure the FastMCP server with registered ABDM tools."""
    mcp = FastMCP("AB Download Manager", instructions=SERVER_INSTRUCTIONS, host=host, port=port)
    if settings is None:
        settings = load_settings()
    service = ABDMService(settings)

    default_mode: Literal["interactive", "headless"] = (
        "headless" if settings.default_mode == "headless" else "interactive"
    )

    @mcp.tool(
        name="abdm_download",
        description=(
            "Submit an HTTP/HTTPS download task to AB Download Manager with multi-threaded acceleration. "
            "In 'interactive' mode, triggers the desktop confirmation GUI. "
            "In 'headless' mode, starts silent background download into allowed sandboxed folder."
        ),
        annotations=DOWNLOAD_ANNOTATIONS,
    )
    async def abdm_download(
        url: str,
        mode: Literal["interactive", "headless"] = default_mode,
        filename: str | None = None,
        subdirectory: str | None = None,
        queue_id: int | None = None,
        category_id: int | None = None,
        headers: dict[str, str] | None = None,
        download_page: str | None = None,
        speed_limit_bytes: int | None = None,
        start_queue: bool = False,
    ) -> DownloadSubmission:
        return await service.download(
            url=url,
            mode=mode,
            filename=filename,
            subdirectory=subdirectory,
            queue_id=queue_id,
            category_id=category_id,
            headers=headers,
            download_page=download_page,
            speed_limit_bytes=speed_limit_bytes,
            start_queue=start_queue,
            protocol="http",
        )

    @mcp.tool(
        name="abdm_download_hls",
        description=(
            "Download an HLS (.m3u8) streaming video/audio task with segment reassembly. "
            "In 'interactive' mode, triggers the desktop confirmation GUI. "
            "In 'headless' mode, starts silent background download into allowed sandboxed folder."
        ),
        annotations=DOWNLOAD_ANNOTATIONS,
    )
    async def abdm_download_hls(
        url: str,
        mode: Literal["interactive", "headless"] = default_mode,
        filename: str | None = None,
        subdirectory: str | None = None,
        queue_id: int | None = None,
        category_id: int | None = None,
        headers: dict[str, str] | None = None,
        download_page: str | None = None,
        speed_limit_bytes: int | None = None,
        start_queue: bool = False,
    ) -> DownloadSubmission:
        return await service.download(
            url=url,
            mode=mode,
            filename=filename,
            subdirectory=subdirectory,
            queue_id=queue_id,
            category_id=category_id,
            headers=headers,
            download_page=download_page,
            speed_limit_bytes=speed_limit_bytes,
            start_queue=start_queue,
            protocol="hls",
        )

    @mcp.tool(
        name="abdm_download_batch",
        description="Enqueue up to 50 URLs in a batch with per-item status tracking.",
        annotations=DOWNLOAD_ANNOTATIONS,
    )
    async def abdm_download_batch(
        urls: list[str],
        mode: Literal["interactive", "headless"] = default_mode,
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
        description="Pause one or more active download tasks by ID.",
        annotations=PAUSE_RESUME_ANNOTATIONS,
    )
    async def abdm_pause(download_id: str | list[str]) -> ActionResult:
        return await service.pause(download_id=download_id)

    @mcp.tool(
        name="abdm_resume",
        description="Resume one or more paused download tasks by ID.",
        annotations=PAUSE_RESUME_ANNOTATIONS,
    )
    async def abdm_resume(download_id: str | list[str]) -> ActionResult:
        return await service.resume(download_id=download_id)

    @mcp.tool(
        name="abdm_pause_all",
        description="Pause all currently active download tasks across AB Download Manager.",
        annotations=PAUSE_RESUME_ANNOTATIONS,
    )
    async def abdm_pause_all() -> ActionResult:
        return await service.pause_all()

    @mcp.tool(
        name="abdm_resume_all",
        description="Resume all currently paused download tasks across AB Download Manager.",
        annotations=PAUSE_RESUME_ANNOTATIONS,
    )
    async def abdm_resume_all() -> ActionResult:
        return await service.resume_all()

    @mcp.tool(
        name="abdm_remove",
        description=(
            "Remove/cancel one or more download tasks. File deletion requires explicit policy "
            "opt-in (ABDM_MCP_ALLOW_FILE_DELETION=true) and path verification."
        ),
        annotations=REMOVE_ANNOTATIONS,
    )
    async def abdm_remove(
        download_id: str | list[str],
        delete_file: bool = False,
    ) -> ActionResult:
        return await service.remove(download_id=download_id, delete_file=delete_file)

    return mcp
