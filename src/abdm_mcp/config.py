"""Configuration discovery and environment management for AB Download Manager MCP."""

import json
import os
import shutil
import sys
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """Configuration settings for ABDM MCP Server."""
    config_dir: Path
    port: int = 15151
    api_key: str | None = None
    cli_path: Path | None = None
    allowed_roots: list[Path]
    allow_private_networks: bool = False
    allow_sensitive_headers: bool = False
    allow_file_deletion: bool = False
    default_mode: str = "interactive"
    max_batch_size: int = 50
    cli_timeout: float = 10.0
    cli_max_output_bytes: int = 1024 * 1024  # 1 MB


def discover_cli_path() -> Path | None:
    """Attempt to locate the AB Download Manager CLI binary."""
    explicit = os.environ.get("ABDM_CLI_PATH")
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p

    # Check PATH first
    for name in ("abdm", "ABDownloadManagerCli", "ab-download-manager-cli"):
        found = shutil.which(name)
        if found:
            return Path(found)

    # Platform-specific standard installation directories
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            win_path = Path(local_app) / "ABDownloadManager" / "ABDownloadManagerCli.exe"
            if win_path.exists():
                return win_path
    elif sys.platform == "darwin":
        mac_path = Path("/Applications/ABDownloadManager.app/Contents/MacOS/ABDownloadManagerCli")
        if mac_path.exists():
            return mac_path
    else:
        # Linux standard locations
        for l_path in [Path.home() / ".local" / "bin" / "abdm", Path("/usr/local/bin/abdm"), Path("/usr/bin/abdm")]:
            if l_path.exists():
                return l_path

    return None


def load_settings() -> Settings:
    """Load settings combining environment variables and ABDM configuration files."""
    # Discover config dir (default ~/.abdm)
    env_cfg = os.environ.get("ABDM_CONFIG_DIR")
    if env_cfg:
        config_dir = Path(env_cfg).resolve()
    else:
        config_dir = (Path.home() / ".abdm").resolve()

    # Discover port: check env, then appSettings.json, then default 15151
    port = 15151
    env_port = os.environ.get("ABDM_PORT")
    if env_port and env_port.isdigit():
        port = int(env_port)
    else:
        settings_file = config_dir / "config" / "appSettings.json"
        if settings_file.exists():
            try:
                with open(settings_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if "browserIntegrationPort" in data:
                        port = int(data["browserIntegrationPort"])
            except Exception:
                pass

    # Discover API key
    api_key = os.environ.get("ABDM_API_KEY")

    # Discover CLI binary
    cli_path = discover_cli_path()

    # Allowed download roots
    env_roots = os.environ.get("ABDM_MCP_ALLOWED_DOWNLOAD_ROOTS")
    if env_roots:
        allowed_roots = [Path(p.strip()).resolve() for p in env_roots.split(",") if p.strip()]
    else:
        # Default strictly to ~/Downloads/ABDM
        default_root = (Path.home() / "Downloads" / "ABDM").resolve()
        allowed_roots = [default_root]

    # Flags
    allow_private = os.environ.get("ABDM_MCP_ALLOW_PRIVATE_NETWORKS", "false").lower() in ("true", "1")
    allow_sensitive = os.environ.get("ABDM_MCP_ALLOW_SENSITIVE_HEADERS", "false").lower() in ("true", "1")
    allow_deletion = os.environ.get("ABDM_MCP_ALLOW_FILE_DELETION", "false").lower() in ("true", "1")
    default_mode = os.environ.get("ABDM_MCP_DEFAULT_MODE", "interactive").lower()
    if default_mode not in ("interactive", "headless"):
        default_mode = "interactive"

    max_batch = 50
    try:
        max_batch = int(os.environ.get("ABDM_MCP_MAX_BATCH_SIZE", "50"))
    except ValueError:
        pass

    return Settings(
        config_dir=config_dir,
        port=port,
        api_key=api_key,
        cli_path=cli_path,
        allowed_roots=allowed_roots,
        allow_private_networks=allow_private,
        allow_sensitive_headers=allow_sensitive,
        allow_file_deletion=allow_deletion,
        default_mode=default_mode,
        max_batch_size=max_batch,
    )
