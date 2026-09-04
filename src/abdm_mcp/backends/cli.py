"""Safe subprocess CLI backend implementation for AB Download Manager."""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from abdm_mcp.backends.base import AbstractBaseBackend
from abdm_mcp.config import Settings
from abdm_mcp.errors import (
    CLIOutputLimitError,
    CLITimeoutError,
    CLIUnavailableError,
    DownloadNotFoundError,
)
from abdm_mcp.models import DownloadInfo


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

    async def _execute_bounded(self, args: List[str]) -> Tuple[int, str, str]:
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
        stdout_chunks: List[bytes] = []
        stderr_chunks: List[bytes] = []
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

        try:
            async with asyncio.timeout(self.settings.cli_timeout):
                await asyncio.gather(
                    read_stream(proc.stdout, True),
                    read_stream(proc.stderr, False),
                    proc.wait(),
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
        filename: Optional[str] = None,
        folder: Optional[str] = None,
        queue_id: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        download_page: Optional[str] = None,
        start: bool = True,
    ) -> str:
        """
        Add an HTTP download task via CLI. Returns the assigned integer download ID.
        """
        args = ["download", "add", "http", "--link", url]
        if filename:
            args.extend(["--name", filename])
        if folder:
            args.extend(["--folder", str(folder)])
        if queue_id is not None:
            args.extend(["--queue", str(queue_id)])
        if download_page:
            args.extend(["--download-page", download_page])
        if start:
            args.append("--start")
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

    async def show_downloads(self, download_id: Optional[str] = None) -> List[DownloadInfo]:
        """
        Query download status using `abdm download show [<id>]`.
        Parses the ASCII box table format.
        """
        args = ["download", "show"]
        if download_id:
            args.append(str(download_id))

        rc, stdout, stderr = await self._execute_bounded(args)
        if rc != 0:
            if download_id and ("not found" in stdout.lower() or "not found" in stderr.lower()):
                raise DownloadNotFoundError(f"Download task #{download_id} not found.")
            raise CLIUnavailableError(f"CLI show failed (exit code {rc}): {stderr or stdout}")

        if "no downloads found" in stdout.lower():
            return []

        # Parse ASCII table rows: ? ID ? Status ? Name ? Folder ?
        # Note: box drawing characters can be '?' or unicode box lines
        results: List[DownloadInfo] = []
        lines = stdout.splitlines()
        row_pattern = re.compile(
            r"^[?|\u2502]\s*(\d+)\s*[?|\u2502]\s*([^?|\u2502]+?)\s*[?|\u2502]\s*([^?|\u2502]+?)\s*[?|\u2502]\s*([^?|\u2502]+?)\s*[?|\u2502]"
        )

        for line in lines:
            line_str = line.strip()
            match = row_pattern.match(line_str)
            if match:
                d_id = match.group(1).strip()
                status = match.group(2).strip()
                name = match.group(3).strip()
                folder = match.group(4).strip()
                # Skip header row if matched
                if d_id.lower() == "id" or status.lower() == "status":
                    continue
                results.append(
                    DownloadInfo(
                        id=d_id,
                        status=status,
                        name=name,
                        folder=folder,
                    )
                )

        if download_id and not results:
            raise DownloadNotFoundError(f"Download #{download_id} not found in CLI output.")

        return results

    async def pause_download(self, download_id: str) -> bool:
        """Pause a download task by ID."""
        rc, stdout, stderr = await self._execute_bounded(["download", "pause", str(download_id)])
        if rc != 0:
            raise CLIUnavailableError(f"Failed to pause download #{download_id}: {stderr or stdout}")
        return True

    async def resume_download(self, download_id: str) -> bool:
        """Resume a download task by ID."""
        rc, stdout, stderr = await self._execute_bounded(["download", "resume", str(download_id)])
        if rc != 0:
            raise CLIUnavailableError(f"Failed to resume download #{download_id}: {stderr or stdout}")
        return True

    async def remove_download(self, download_id: str) -> bool:
        """Remove a download task by ID."""
        rc, stdout, stderr = await self._execute_bounded(["download", "remove", str(download_id)])
        if rc != 0:
            raise CLIUnavailableError(f"Failed to remove download #{download_id}: {stderr or stdout}")
        return True
