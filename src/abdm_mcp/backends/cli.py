"""Safe subprocess CLI backend implementation for AB Download Manager."""

import asyncio
import re
from typing import Literal

from abdm_mcp.backends.base import AbstractBaseBackend
from abdm_mcp.config import Settings
from abdm_mcp.errors import (
    CLIOutputLimitError,
    CLITimeoutError,
    CLIUnavailableError,
    DownloadNotFoundError,
)
from abdm_mcp.models import DownloadInfo

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from console text."""
    return ANSI_ESCAPE_RE.sub("", text)


class CliBackend(AbstractBaseBackend):
    """Subprocess client executing ABDownloadManagerCli with streaming buffer limits."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.cli_path = settings.cli_path

    async def is_available(self) -> bool:
        """Check if the CLI executable exists and runs."""
        if not self.cli_path or not self.cli_path.exists():
            return False
        try:
            rc, stdout, _ = await self._execute_bounded(["--version"])
            return rc == 0
        except Exception:
            return False

    async def start_if_not_started(self) -> bool:
        """
        Ensure the AB Download Manager desktop application is running.
        Invokes `abdm gui start-if-not-started`.
        """
        if not self.cli_path or not self.cli_path.exists():
            return False
        try:
            rc, stdout, stderr = await self._execute_bounded(["gui", "start-if-not-started"])
            return rc == 0
        except Exception:
            return False

    async def get_integration_port(self) -> int | None:
        """
        Query the active integration port via `abdm gui integration show`.
        Returns the parsed integer port or None if unavailable.
        """
        if not self.cli_path or not self.cli_path.exists():
            return None
        try:
            rc, stdout, stderr = await self._execute_bounded(["gui", "integration", "show"])
            if rc == 0 and stdout:
                clean = strip_ansi(stdout).strip()
                match = re.search(r"\b(\d{2,5})\b", clean)
                if match:
                    port = int(match.group(1))
                    if 1 <= port <= 65535:
                        return port
            return None
        except Exception:
            return None

    async def get_version(self) -> str | None:
        """Query and parse the AB Download Manager CLI version."""
        if not self.cli_path or not self.cli_path.exists():
            return None
        try:
            rc, stdout, _ = await self._execute_bounded(["--version"])
            if rc == 0 and stdout:
                clean_stdout = strip_ansi(stdout)
                match = re.search(r"version\s+([0-9.]+)", clean_stdout, re.IGNORECASE)
                if match:
                    return match.group(1)
                first_line = clean_stdout.strip().splitlines()[0]
                return first_line
            return None
        except Exception:
            return None

    async def _execute_bounded(self, args: list[str]) -> tuple[int, str, str]:
        """
        Safely execute a CLI command using create_subprocess_exec (NO shell).
        Enforces execution timeout and maximum streaming output limits.
        """
        if not self.cli_path or not self.cli_path.exists():
            raise CLIUnavailableError("AB Download Manager CLI binary not found.")

        cmd = [str(self.cli_path)] + args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        max_bytes = self.settings.cli_max_output_bytes
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        total_stdout = 0
        total_stderr = 0

        async def read_stream(stream: asyncio.StreamReader, is_stdout: bool):
            nonlocal total_stdout, total_stderr
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                if is_stdout:
                    total_stdout += len(chunk)
                    stdout_chunks.append(chunk)
                    if total_stdout > max_bytes:
                        try:
                            proc.kill()
                        except ProcessLookupError:
                            pass
                        raise CLIOutputLimitError(f"CLI stdout exceeded {max_bytes} bytes buffer limit.")
                else:
                    total_stderr += len(chunk)
                    stderr_chunks.append(chunk)
                    if total_stderr > max_bytes:
                        try:
                            proc.kill()
                        except ProcessLookupError:
                            pass
                        raise CLIOutputLimitError(f"CLI stderr exceeded {max_bytes} bytes buffer limit.")

        if proc.stdout is None or proc.stderr is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise CLIUnavailableError("Subprocess failed to establish stdout/stderr pipes.")

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, True),
                    read_stream(proc.stderr, False),
                    proc.wait(),
                ),
                timeout=self.settings.cli_timeout,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise CLITimeoutError(f"CLI command timed out after {self.settings.cli_timeout}s.")

        stdout_text = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        return proc.returncode or 0, stdout_text, stderr_text

    async def add_download(
        self,
        url: str,
        filename: str | None = None,
        folder: str | None = None,
        queue_id: int | None = None,
        category_id: int | None = None,
        headers: dict[str, str] | None = None,
        download_page: str | None = None,
        start: bool = True,
        start_queue: bool = False,
        protocol: Literal["http", "hls"] = "http",
    ) -> str:
        """
        Add an HTTP or HLS download task via CLI. Returns the assigned integer download ID.
        """
        subcommand = "hls" if protocol == "hls" else "http"
        args = ["download", "add", subcommand, "--link", url]
        if filename:
            args.extend(["--name", filename])
        if folder:
            args.extend(["--folder", str(folder)])
        if queue_id is not None:
            args.extend(["--queue", str(queue_id)])
        if category_id is not None:
            args.extend(["--category", str(category_id)])
        if download_page:
            args.extend(["--download-page", download_page])
        if start:
            args.append("--start")
        if start_queue:
            args.append("--start-queue")
        if headers:
            for k, v in headers.items():
                args.extend(["--header", f"{k}: {v}"])

        rc, stdout, stderr = await self._execute_bounded(args)
        if rc != 0:
            raise CLIUnavailableError(f"CLI failed to add download (exit code {rc}): {stderr or stdout}")

        # The CLI outputs the new download ID directly on stdout (e.g. '17\n')
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        for line in lines:
            if line.isdigit():
                return line

        # If not on its own line, search for digit
        match = re.search(r"\b(\d+)\b", stdout)
        if match:
            return match.group(1)

        raise CLIUnavailableError(f"Could not parse download ID from CLI output: {stdout}")

    async def show_downloads(
        self, download_ids: list[str] | str | None = None
    ) -> list[DownloadInfo]:
        """
        Query download status using `abdm download show [<id>...]`.
        Parses ASCII / Unicode table format, stripping ANSI styling.
        """
        args = ["download", "show"]
        requested_ids: list[str] = []
        if isinstance(download_ids, str):
            requested_ids = [download_ids.strip()]
        elif isinstance(download_ids, (list, tuple, set)):
            requested_ids = [str(d).strip() for d in download_ids if str(d).strip()]

        if requested_ids:
            args.extend(requested_ids)

        rc, stdout, stderr = await self._execute_bounded(args)
        if rc != 0:
            if requested_ids and ("not found" in stdout.lower() or "not found" in stderr.lower()):
                raise DownloadNotFoundError(f"Download task(s) {requested_ids} not found.")
            raise CLIUnavailableError(f"CLI show failed (exit code {rc}): {stderr or stdout}")

        clean_stdout = strip_ansi(stdout)
        if "no downloads found" in clean_stdout.lower():
            return []

        results: list[DownloadInfo] = []
        for line in clean_stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            # Split line on vertical border characters (Unicode light/double or ASCII | / ?)
            parts = re.split(r"[\u2502\u2551|?]", line_str)
            if len(parts) >= 5:
                cells = [c.strip() for c in parts[1:-1]]
                if len(cells) >= 4:
                    d_id, status, name, folder = cells[0], cells[1], cells[2], cells[3]
                    if d_id.lower() == "id" or status.lower() == "status":
                        continue
                    if d_id.isdigit():
                        results.append(
                            DownloadInfo(
                                id=d_id,
                                status=status,
                                name=name,
                                folder=folder,
                            )
                        )

        if requested_ids and not results:
            raise DownloadNotFoundError(f"Download task(s) {requested_ids} not found in CLI output.")

        return results

    async def pause_download(self, download_ids: list[str] | str) -> bool:
        """Pause one or more download tasks by ID."""
        ids = [download_ids] if isinstance(download_ids, str) else list(download_ids)
        rc, stdout, stderr = await self._execute_bounded(["download", "pause"] + [str(i) for i in ids])
        if rc != 0:
            raise CLIUnavailableError(f"Failed to pause download(s) {ids}: {stderr or stdout}")
        return True

    async def resume_download(self, download_ids: list[str] | str) -> bool:
        """Resume one or more download tasks by ID."""
        ids = [download_ids] if isinstance(download_ids, str) else list(download_ids)
        rc, stdout, stderr = await self._execute_bounded(["download", "resume"] + [str(i) for i in ids])
        if rc != 0:
            raise CLIUnavailableError(f"Failed to resume download(s) {ids}: {stderr or stdout}")
        return True

    async def remove_download(self, download_ids: list[str] | str) -> bool:
        """Remove one or more download tasks by ID."""
        ids = [download_ids] if isinstance(download_ids, str) else list(download_ids)
        rc, stdout, stderr = await self._execute_bounded(["download", "remove"] + [str(i) for i in ids])
        if rc != 0:
            raise CLIUnavailableError(f"Failed to remove download(s) {ids}: {stderr or stdout}")
        return True
