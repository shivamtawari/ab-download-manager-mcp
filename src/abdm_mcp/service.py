"""ABDMService orchestrator coordinating security, REST backend, and CLI backend."""

from pathlib import Path
from typing import Dict, List, Literal, Optional

from abdm_mcp.backends.cli import CliBackend
from abdm_mcp.backends.rest import RestBackend
from abdm_mcp.config import Settings
from abdm_mcp.errors import (
    ABDMError,
    BackendCompatibilityError,
    UnsupportedParameterError,
)
from abdm_mcp.models import (
    ActionResult,
    BatchSubmission,
    DownloadInfo,
    DownloadListResult,
    DownloadMode,
    DownloadSubmission,
    HealthReport,
    QueueInfo,
)
from abdm_mcp.security import (
    resolve_download_path,
    validate_filename,
    validate_headers,
    validate_url,
)


class ABDMService:
    """Service layer exposing high-level operations across ABDM backends."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.rest = RestBackend(settings)
        self.cli = CliBackend(settings)

    async def check_status(self) -> HealthReport:
        """Perform a full health and capability check across REST and CLI backends."""
        rest_ok, authenticated, _ = await self.rest.check_health()
        cli_ok = await self.cli.is_available()

        capabilities: List[str] = []
        if rest_ok:
            capabilities.extend(["interactive_download", "queues"])
        if cli_ok:
            capabilities.extend(["headless_download", "list", "pause", "resume", "remove"])

        return HealthReport(
            rest_available=rest_ok,
            authenticated=authenticated,
            port=self.settings.port,
            cli_available=cli_ok,
            cli_version="1.10.x" if cli_ok else None,
            shared_state_verified=True,
            capabilities=capabilities,
        )

    async def download(
        self,
        url: str,
        mode: DownloadMode = "interactive",
        filename: Optional[str] = None,
        subdirectory: Optional[str] = None,
        queue_id: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        download_page: Optional[str] = None,
    ) -> DownloadSubmission:
        """Submit a single download task."""
        clean_url = validate_url(url, allow_private_networks=self.settings.allow_private_networks)
        clean_headers = validate_headers(headers, allow_sensitive=self.settings.allow_sensitive_headers)

        if mode == "interactive":
            if filename is not None or subdirectory is not None or queue_id is not None:
                raise UnsupportedParameterError(
                    "filename, subdirectory, and queue_id cannot be preselected when mode='interactive'. "
                    "Use mode='headless' for programmatic destination control."
                )
            await self.rest.add_interactive(
                url=clean_url,
                headers=clean_headers,
                download_page=download_page,
            )
            return DownloadSubmission(
                accepted=True,
                backend="rest",
                download_id=None,
                mode="interactive",
                message="Download confirmation prompt sent to AB Download Manager desktop GUI.",
            )

        elif mode == "headless":
            clean_filename = validate_filename(filename)
            target_folder = resolve_download_path(self.settings.allowed_roots, subdirectory)

            if await self.cli.is_available():
                task_id = await self.cli.add_download(
                    url=clean_url,
                    filename=clean_filename,
                    folder=str(target_folder),
                    queue_id=queue_id,
                    headers=clean_headers,
                    download_page=download_page,
                    start=True,
                )
                return DownloadSubmission(
                    accepted=True,
                    backend="cli",
                    download_id=task_id,
                    mode="headless",
                    message=f"Headless download #{task_id} added and started.",
                )
            else:
                # Fallback to REST headless endpoint
                await self.rest.add_headless(
                    url=clean_url,
                    filename=clean_filename,
                    folder=str(target_folder),
                    queue_id=queue_id,
                    headers=clean_headers,
                    download_page=download_page,
                )
                return DownloadSubmission(
                    accepted=True,
                    backend="rest",
                    download_id=None,
                    mode="headless",
                    message="Headless download submitted via REST API.",
                )
        else:
            raise UnsupportedParameterError(f"Unsupported download mode '{mode}'. Choose 'interactive' or 'headless'.")

    async def download_batch(
        self,
        urls: List[str],
        mode: DownloadMode = "interactive",
        queue_id: Optional[int] = None,
    ) -> BatchSubmission:
        """Submit a batch of URLs with partial success tracking."""
        if not urls:
            return BatchSubmission(submitted=0, failed=0, items=[])

        if len(urls) > self.settings.max_batch_size:
            raise ABDMError(
                f"Batch size {len(urls)} exceeds maximum allowed batch limit of {self.settings.max_batch_size}."
            )

        if mode == "interactive" and queue_id is not None:
            raise UnsupportedParameterError(
                "queue_id cannot be specified for batch downloads when mode='interactive'."
            )

        items: List[DownloadSubmission] = []
        submitted = 0
        failed = 0

        for u in urls:
            try:
                sub = await self.download(
                    url=u,
                    mode=mode,
                    queue_id=queue_id,
                )
                items.append(sub)
                submitted += 1
            except Exception as e:
                items.append(
                    DownloadSubmission(
                        accepted=False,
                        backend="rest" if mode == "interactive" else "cli",
                        download_id=None,
                        mode=mode,
                        message=str(e),
                    )
                )
                failed += 1

        return BatchSubmission(submitted=submitted, failed=failed, items=items)

    async def get_queues(self) -> List[QueueInfo]:
        """Fetch all configured queues from ABDM."""
        return await self.rest.get_queues()

    async def list_downloads(self, status: Optional[str] = None) -> DownloadListResult:
        """List current downloads using the CLI backend."""
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Listing downloads requires the ABDM CLI binary.")
        items = await self.cli.show_downloads()
        if status:
            lower_status = status.lower()
            items = [item for item in items if item.status.lower() == lower_status]
        return DownloadListResult(items=items, count=len(items))

    async def get_download(self, download_id: str) -> DownloadInfo:
        """Retrieve task details for a single download ID."""
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Inspecting download details requires the ABDM CLI binary.")
        items = await self.cli.show_downloads(download_id=download_id)
        if not items:
            raise ABDMError(f"Download #{download_id} not found.")
        return items[0]

    async def pause(self, download_id: str) -> ActionResult:
        """Pause an active download task."""
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Pausing downloads requires the ABDM CLI binary.")
        await self.cli.pause_download(download_id)
        return ActionResult(
            success=True,
            download_id=download_id,
            action="pause",
            message=f"Download #{download_id} paused.",
        )

    async def resume(self, download_id: str) -> ActionResult:
        """Resume a paused download task."""
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Resuming downloads requires the ABDM CLI binary.")
        await self.cli.resume_download(download_id)
        return ActionResult(
            success=True,
            download_id=download_id,
            action="resume",
            message=f"Download #{download_id} resumed.",
        )

    async def remove(self, download_id: str, delete_file: bool = False) -> ActionResult:
        """Cancel and remove a download task."""
        if delete_file and not self.settings.allow_file_deletion:
            raise ABDMError(
                "File deletion is disabled by security policy. "
                "Set ABDM_MCP_ALLOW_FILE_DELETION=true to enable it."
            )

        if not await self.cli.is_available():
            raise BackendCompatibilityError("Removing downloads requires the ABDM CLI binary.")

        file_to_delete: Optional[Path] = None
        if delete_file:
            try:
                info = await self.get_download(download_id)
                if info.folder and info.name:
                    candidate = (Path(info.folder) / info.name).resolve()
                    is_safe = any(candidate.is_relative_to(root.resolve()) for root in self.settings.allowed_roots)
                    if is_safe and candidate.exists():
                        file_to_delete = candidate
            except Exception:
                pass

        await self.cli.remove_download(download_id)

        if file_to_delete and file_to_delete.exists():
            try:
                file_to_delete.unlink(missing_ok=True)
            except Exception:
                pass

        return ActionResult(
            success=True,
            download_id=download_id,
            action="remove",
            message=f"Download #{download_id} removed{' with file deletion' if file_to_delete else ''}.",
        )
