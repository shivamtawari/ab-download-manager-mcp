"""Pydantic schemas and typed data models for AB Download Manager MCP Server."""

from typing import Literal

from pydantic import BaseModel, Field

DownloadMode = Literal["interactive", "headless"]
DownloadStatus = Literal["Downloading", "Paused", "Completed", "Error", "Unknown"]


class DownloadSubmission(BaseModel):
    """Result of submitting a download request."""
    accepted: bool = Field(description="Whether the task was accepted by ABDM")
    backend: Literal["rest", "cli"] = Field(description="Which backend processed the request")
    download_id: str | None = Field(default=None, description="Assigned task ID if available")
    mode: DownloadMode = Field(description="Mode under which download was created")
    protocol: Literal["http", "hls"] = Field(default="http", description="Download protocol (http or hls)")
    message: str | None = Field(default=None, description="Status or error message")


class BatchSubmission(BaseModel):
    """Summary result of submitting a batch of download requests."""
    submitted: int = Field(description="Number of successfully submitted URLs")
    failed: int = Field(description="Number of failed submissions")
    items: list[DownloadSubmission] = Field(default_factory=list, description="Per-URL results")


class ActionResult(BaseModel):
    """Result of an action performed on download task(s) (pause, resume, remove)."""
    success: bool = Field(description="Whether the action succeeded")
    download_id: str | None = Field(default=None, description="Target download task ID if single")
    download_ids: list[str] = Field(default_factory=list, description="Target download task IDs affected")
    count: int = Field(default=1, description="Number of tasks affected")
    action: str = Field(description="Action name (e.g. pause, resume, remove, pause_all, resume_all)")
    message: str | None = Field(default=None, description="Details or error message")


class QueueInfo(BaseModel):
    """Information about an ABDM download queue."""
    id: int = Field(description="Queue identifier")
    name: str = Field(description="Human-readable queue name")


class DownloadInfo(BaseModel):
    """Detailed information about an individual download task."""
    id: str = Field(description="Unique task identifier")
    name: str | None = Field(default=None, description="File name")
    status: str = Field(description="Current task status (e.g. Paused, Downloading, Completed, Error)")
    folder: str | None = Field(default=None, description="Destination folder")
    url: str | None = Field(default=None, description="Source URL")
    queue_id: int | None = Field(default=None, description="Associated queue ID")


class DownloadListResult(BaseModel):
    """List of downloads currently reported by the system."""
    items: list[DownloadInfo] = Field(default_factory=list, description="List of downloads")
    count: int = Field(description="Total count of items returned")


class HealthReport(BaseModel):
    """Health and capability report of the connected AB Download Manager system."""
    rest_available: bool = Field(description="Whether the local REST integration port is reachable")
    authenticated: bool | None = Field(default=None, description="Whether authentication was verified")
    port: int = Field(description="Resolved active port")
    cli_available: bool = Field(description="Whether the ABDM CLI binary is present and operational")
    cli_version: str | None = Field(default=None, description="CLI version if detected")
    shared_state_verified: bool = Field(description="Whether REST and CLI have been verified to share state")
    capabilities: list[str] = Field(default_factory=list, description="List of supported operations")
