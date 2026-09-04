"""Ktor REST backend implementation for AB Download Manager."""

from typing import Any, Dict, List, Optional, Tuple
import httpx

from abdm_mcp.backends.base import AbstractBaseBackend
from abdm_mcp.config import Settings
from abdm_mcp.errors import ABDMAuthenticationError, ABDMUnavailableError
from abdm_mcp.models import QueueInfo


class RestBackend(AbstractBaseBackend):
    """HTTP client communicating with the AB Download Manager local Ktor server."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = f"http://127.0.0.1:{settings.port}"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.settings.api_key:
            headers["X-API-Key"] = self.settings.api_key
        return headers

    async def is_available(self) -> bool:
        """Check if the REST server is reachable via GET /queues."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/queues", headers=self._get_headers())
                return resp.status_code in (200, 401, 403)
        except Exception:
            return False

    async def check_health(self) -> Tuple[bool, Optional[bool], List[QueueInfo]]:
        """
        Probe the REST endpoint and return (reachable, authenticated, queues).
        """
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/queues", headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    queues = [QueueInfo(id=q["id"], name=q["name"]) for q in data]
                    return True, True, queues
                elif resp.status_code in (401, 403):
                    return True, False, []
                else:
                    return False, None, []
        except httpx.ConnectError:
            return False, None, []
        except Exception:
            return False, None, []

    async def get_queues(self) -> List[QueueInfo]:
        """Fetch configured queues via GET /queues."""
        url = f"{self.base_url}/queues"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=self._get_headers())
                if resp.status_code in (401, 403):
                    raise ABDMAuthenticationError(
                        "Authentication failed for ABDM REST API. Check your ABDM_API_KEY."
                    )
                resp.raise_for_status()
                data = resp.json()
                return [QueueInfo(id=q["id"], name=q["name"]) for q in data]
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ABDMUnavailableError(
                f"Cannot connect to AB Download Manager on port {self.settings.port}. Is the app running?"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ABDMUnavailableError(f"HTTP error {e.response.status_code} from ABDM REST API.") from e

    async def add_interactive(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        download_page: Optional[str] = None,
    ) -> bool:
        """
        Submit a download task that triggers the ABDM GUI confirmation dialog via POST /add.
        """
        endpoint = f"{self.base_url}/add"
        payload = [
            {
                "link": url,
                "headers": headers or {},
                "downloadPage": download_page or "",
            }
        ]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(endpoint, json=payload, headers=self._get_headers())
                if resp.status_code in (401, 403):
                    raise ABDMAuthenticationError("Authentication failed for ABDM REST API.")
                resp.raise_for_status()
                return resp.status_code in (200, 201)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ABDMUnavailableError(f"Cannot connect to ABDM on port {self.settings.port}.") from e

    async def add_headless(
        self,
        url: str,
        filename: Optional[str] = None,
        folder: Optional[str] = None,
        queue_id: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        download_page: Optional[str] = None,
    ) -> bool:
        """
        Submit a headless download task without displaying a GUI popup via POST /start-headless-download.
        """
        endpoint = f"{self.base_url}/start-headless-download"
        payload: Dict[str, Any] = {
            "downloadSource": {
                "link": url,
                "headers": headers or {},
                "downloadPage": download_page or "",
            },
            "name": filename or "",
            "folder": folder or "",
            "queueId": queue_id if queue_id is not None else 0,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(endpoint, json=payload, headers=self._get_headers())
                if resp.status_code in (401, 403):
                    raise ABDMAuthenticationError("Authentication failed for ABDM REST API.")
                resp.raise_for_status()
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ABDMUnavailableError(f"Cannot connect to ABDM on port {self.settings.port}.") from e
