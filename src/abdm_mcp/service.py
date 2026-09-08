"""ABDMService orchestrator coordinating security, REST backend, and CLI backend."""

import asyncio
from pathlib import Path
from typing import Literal

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

STATUS_FILTER_MAP: dict[str, set[str]] = {
    "active": {"active", "downloading"},
    "paused": {"paused"},
    "completed": {"completed", "finished"},
    "error": {"error", "failed"},
}


class ABDMService:
    """Service layer exposing high-level operations across ABDM backends."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.rest = RestBackend(settings)
        self.cli = CliBackend(settings)

    async def ensure_app_ready(self) -> bool:
        """
        Verify that ABDM is running, auto-launch it if configured and offline,
        and dynamically auto-discover the live integration port if possible.
        """
        # 1. Probe REST endpoint with current port
        rest_ok = await self.rest.is_available()

        # 2. If REST unreachable and auto-discover enabled, try discovering port via CLI
        if not rest_ok and self.settings.auto_discover_port and await self.cli.is_available():
            discovered_port = await self.cli.get_integration_port()
            if discovered_port and discovered_port != self.rest.port:
                self.rest.set_port(discovered_port)
                rest_ok = await self.rest.is_available()

        # 3. If still not ok and auto_start_app enabled, wake the app via CLI
        if not rest_ok and self.settings.auto_start_app and await self.cli.is_available():
            started = await self.cli.start_if_not_started()
            if started:
                for _ in range(4):
                    if await self.rest.is_available():
                        rest_ok = True
                        break
                    await asyncio.sleep(0.2)
                    if self.settings.auto_discover_port:
                        discovered_port = await self.cli.get_integration_port()
                        if discovered_port and discovered_port != self.rest.port:
                            self.rest.set_port(discovered_port)

        return rest_ok

    async def check_status(self) -> HealthReport:
        """Perform a full health and capability check across REST and CLI backends."""
        await self.ensure_app_ready()
        rest_ok, authenticated, _ = await self.rest.check_health()
        cli_ok = await self.cli.is_available()
        cli_version = await self.cli.get_version() if cli_ok else None

        capabilities: list[str] = []
        if rest_ok:
            capabilities.extend(["interactive_download", "queues"])
        if cli_ok:
            capabilities.extend(["headless_download", "list", "pause", "resume", "remove"])

        return HealthReport(
            rest_available=rest_ok,
            authenticated=authenticated,
            port=self.rest.port,
            cli_available=cli_ok,
            cli_version=cli_version,
            shared_state_verified=bool(rest_ok and cli_ok),
            capabilities=capabilities,
        )

    async def download(
        self,
        url: str,
        mode: DownloadMode | None = None,
        filename: str | None = None,
        subdirectory: str | None = None,
        queue_id: int | None = None,
        category_id: int | None = None,
        headers: dict[str, str] | None = None,
        download_page: str | None = None,
        speed_limit_bytes: int | None = None,
        start_queue: bool = False,
        protocol: Literal["http", "hls"] = "http",
    ) -> DownloadSubmission:
        if mode is None:
            mode = "headless" if self.settings.default_mode == "headless" else "interactive"
        clean_url = validate_url(url, allow_private_networks=self.settings.allow_private_networks)
        clean_headers = validate_headers(headers, allow_sensitive=self.settings.allow_sensitive_headers)

        if mode == "interactive":
            if (
                filename is not None
                or subdirectory is not None
                or queue_id is not None
                or category_id is not None
                or speed_limit_bytes is not None
            ):
                raise UnsupportedParameterError(
                    "filename, subdirectory, queue_id, category_id, and speed_limit_bytes cannot be preselected when mode='interactive'. "
                    "Use mode='headless' for programmatic destination and throttle control."
                )
            await self.ensure_app_ready()
            await self.rest.add_interactive(
                url=clean_url,
                headers=clean_headers,
                download_page=download_page,
                protocol=protocol,
            )
            return DownloadSubmission(
                accepted=True,
                backend="rest",
                download_id=None,
                mode="interactive",
                protocol=protocol,
                message="Download confirmation prompt sent to AB Download Manager desktop GUI.",
            )

        elif mode == "headless":
            clean_filename = validate_filename(filename)
            target_folder = resolve_download_path(self.settings.allowed_roots, subdirectory)
            await self.ensure_app_ready()

            if await self.cli.is_available():
                task_id = await self.cli.add_download(
                    url=clean_url,
                    filename=clean_filename,
                    folder=str(target_folder),
                    queue_id=queue_id,
                    category_id=category_id,
                    headers=clean_headers,
                    download_page=download_page,
                    start=True,
                    start_queue=start_queue,
                    protocol=protocol,
                )
                return DownloadSubmission(
                    accepted=True,
                    backend="cli",
                    download_id=task_id,
                    mode="headless",
                    protocol=protocol,
                    message=f"Headless {protocol.upper()} download #{task_id} added and started.",
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
                    speed_limit=speed_limit_bytes,
                    start_queue=start_queue,
                    protocol=protocol,
                )
                return DownloadSubmission(
                    accepted=True,
                    backend="rest",
                    download_id=None,
                    mode="headless",
                    protocol=protocol,
                    message=f"Headless {protocol.upper()} download submitted via REST API.",
                )
        else:
            raise UnsupportedParameterError(f"Unsupported download mode '{mode}'. Choose 'interactive' or 'headless'.")

    async def download_batch(
        self,
        urls: list[str],
        mode: DownloadMode | None = None,
        queue_id: int | None = None,
    ) -> BatchSubmission:
        """Submit a batch of URLs with partial success tracking."""
        if mode is None:
            mode = "headless" if self.settings.default_mode == "headless" else "interactive"

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

        items: list[DownloadSubmission] = []
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
                failing_backend: Literal["rest", "cli"] = "rest"
                if mode == "headless" and await self.cli.is_available():
                    failing_backend = "cli"

                items.append(
                    DownloadSubmission(
                        accepted=False,
                        backend=failing_backend,
                        download_id=None,
                        mode=mode,
                        message=str(e),
                    )
                )
                failed += 1

        return BatchSubmission(submitted=submitted, failed=failed, items=items)

    async def get_queues(self) -> list[QueueInfo]:
        """Fetch all configured queues from ABDM."""
        await self.ensure_app_ready()
        return await self.rest.get_queues()

    async def list_downloads(self, status: str | None = None) -> DownloadListResult:
        """List current downloads using the CLI backend."""
        await self.ensure_app_ready()
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Listing downloads requires the ABDM CLI binary.")
        items = await self.cli.show_downloads()
        if status:
            lower_status = status.lower()
            target_statuses = STATUS_FILTER_MAP.get(lower_status, {lower_status})
            items = [item for item in items if item.status.lower() in target_statuses]
        return DownloadListResult(items=items, count=len(items))

    async def get_download(self, download_id: str) -> DownloadInfo:
        """Retrieve task details for a single download ID."""
        await self.ensure_app_ready()
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Inspecting download details requires the ABDM CLI binary.")
        items = await self.cli.show_downloads(download_ids=download_id)
        if not items:
            raise ABDMError(f"Download #{download_id} not found.")
        return items[0]

    async def pause(self, download_id: str | list[str]) -> ActionResult:
        """Pause one or more active download tasks."""
        await self.ensure_app_ready()
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Pausing downloads requires the ABDM CLI binary.")
        ids = [download_id] if isinstance(download_id, str) else list(download_id)
        if not ids:
            return ActionResult(
                success=True,
                download_id=None,
                download_ids=[],
                count=0,
                action="pause",
                message="No download IDs provided.",
            )
        await self.cli.pause_download(ids)
        return ActionResult(
            success=True,
            download_id=ids[0] if len(ids) == 1 else None,
            download_ids=ids,
            count=len(ids),
            action="pause",
            message=f"Paused {len(ids)} download task(s): {', '.join(ids)}.",
        )

    async def resume(self, download_id: str | list[str]) -> ActionResult:
        """Resume one or more paused download tasks."""
        await self.ensure_app_ready()
        if not await self.cli.is_available():
            raise BackendCompatibilityError("Resuming downloads requires the ABDM CLI binary.")
        ids = [download_id] if isinstance(download_id, str) else list(download_id)
        if not ids:
            return ActionResult(
                success=True,
                download_id=None,
                download_ids=[],
                count=0,
                action="resume",
                message="No download IDs provided.",
            )
        await self.cli.resume_download(ids)
        return ActionResult(
            success=True,
            download_id=ids[0] if len(ids) == 1 else None,
            download_ids=ids,
            count=len(ids),
            action="resume",
            message=f"Resumed {len(ids)} download task(s): {', '.join(ids)}.",
        )

    async def pause_all(self) -> ActionResult:
        """Pause all currently active download tasks."""
        await self.ensure_app_ready()
        active_downloads = await self.list_downloads(status="active")
        if not active_downloads.items:
            return ActionResult(
                success=True,
                download_id=None,
                download_ids=[],
                count=0,
                action="pause_all",
                message="No active downloads to pause.",
            )
        ids = [item.id for item in active_downloads.items]
        res = await self.pause(download_id=ids)
        res.action = "pause_all"
        return res

    async def resume_all(self) -> ActionResult:
        """Resume all currently paused download tasks."""
        await self.ensure_app_ready()
        paused_downloads = await self.list_downloads(status="paused")
        if not paused_downloads.items:
            return ActionResult(
                success=True,
                download_id=None,
                download_ids=[],
                count=0,
                action="resume_all",
                message="No paused downloads to resume.",
            )
        ids = [item.id for item in paused_downloads.items]
        res = await self.resume(download_id=ids)
        res.action = "resume_all"
        return res

    async def remove(self, download_id: str | list[str], delete_file: bool = False) -> ActionResult:
        """Cancel and remove one or more download tasks."""
        await self.ensure_app_ready()
        if delete_file and not self.settings.allow_file_deletion:
            raise ABDMError(
                "File deletion is disabled by security policy. "
                "Set ABDM_MCP_ALLOW_FILE_DELETION=true to enable it."
            )

        if not await self.cli.is_available():
            raise BackendCompatibilityError("Removing downloads requires the ABDM CLI binary.")

        ids = [download_id] if isinstance(download_id, str) else list(download_id)
        if not ids:
            return ActionResult(
                success=True,
                download_id=None,
                download_ids=[],
                count=0,
                action="remove",
                message="No download IDs provided.",
            )

        files_to_delete: list[Path] = []
        if delete_file:
            for single_id in ids:
                try:
                    info = await self.get_download(single_id)
                    if info.folder and info.name:
                        candidate = (Path(info.folder) / info.name).resolve()
                        is_safe = any(candidate.is_relative_to(root.resolve()) for root in self.settings.allowed_roots)
                        if is_safe and candidate.exists():
                            files_to_delete.append(candidate)
                except Exception:
                    pass

        await self.cli.remove_download(ids)

        deleted_count = 0
        for f in files_to_delete:
            if f.exists():
                try:
                    f.unlink(missing_ok=True)
                    deleted_count += 1
                except Exception:
                    pass

        del_msg = f" with {deleted_count} file(s) deleted" if delete_file else ""
        return ActionResult(
            success=True,
            download_id=ids[0] if len(ids) == 1 else None,
            download_ids=ids,
            count=len(ids),
            action="remove",
            message=f"Removed {len(ids)} download task(s){del_msg}.",
        )
