"""Security, sanitization, and sandboxing guards for AB Download Manager MCP."""

import ipaddress
import socket
import urllib.parse
from pathlib import Path

from abdm_mcp.errors import (
    SensitiveHeaderError,
    UnsafeFilenameError,
    UnsafePathError,
    UnsafeURLError,
)

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

SENSITIVE_HEADERS = {
    "cookie",
    "authorization",
    "proxy-authorization",
    "host",
}


def validate_url(url: str, allow_private_networks: bool = False) -> str:
    """
    Validate that the given URL uses an allowed scheme and does not target private networks.
    
    Note on SSRF limitations: This check performs best-effort pre-dispatch blocking of direct
    loopback, private, and link-local destinations. It cannot guarantee immunity against
    DNS rebinding or downstream 302 redirects performed by AB Download Manager.
    """
    if not url or not isinstance(url, str):
        raise UnsafeURLError("URL must be a non-empty string.")

    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL must have a valid hostname.")

    if allow_private_networks:
        return url.strip()

    # Direct hostname checks
    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1"):
        raise UnsafeURLError(f"Access to localhost/loopback target '{hostname}' is blocked by security policy.")

    # Check IP directly or perform resolution check
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise UnsafeURLError(f"Target IP {ip} is in a private or restricted range.")
    except ValueError:
        # Hostname is not an IP literal; attempt pre-dispatch DNS inspection
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    raise UnsafeURLError(
                        f"Target host '{hostname}' resolves to restricted IP {ip_str}."
                    )
        except socket.gaierror:
            # Let ABDM handle DNS failures downstream if it cannot resolve
            pass

    return url.strip()


def validate_filename(filename: str | None) -> str | None:
    """
    Sanitize and validate that a filename contains no path traversal sequences or illegal characters.
    """
    if filename is None:
        return None

    cleaned = filename.strip()
    if not cleaned:
        raise UnsafeFilenameError("Filename cannot be an empty string.")

    if cleaned in (".", ".."):
        raise UnsafeFilenameError(f"Illegal filename '{cleaned}'.")

    if "/" in cleaned or "\\" in cleaned:
        raise UnsafeFilenameError(f"Filename '{cleaned}' must not contain directory separators ('/' or '\\').")

    if ":" in cleaned:
        raise UnsafeFilenameError(f"Filename '{cleaned}' must not contain drive or stream prefixes (':').")

    if any(ord(c) < 32 for c in cleaned):
        raise UnsafeFilenameError("Filename contains illegal control characters.")

    # Check for Windows reserved names (e.g. CON, NUL, COM1, CON.txt)
    normalized = cleaned.rstrip(" .")
    stem = normalized.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise UnsafeFilenameError(f"Filename '{cleaned}' matches reserved device name '{stem}'.")

    return cleaned


def resolve_download_path(
    allowed_roots: list[Path],
    subdirectory: str | None = None,
) -> Path:
    """
    Safely resolve a download destination directory within the configured allowed sandbox roots.
    Supports targeting any configured allowed root via absolute path or root folder name prefix.
    """
    if not allowed_roots:
        raise UnsafePathError("No allowed download roots are configured.")

    resolved_roots = [r.resolve() for r in allowed_roots]

    if not subdirectory or not subdirectory.strip():
        return resolved_roots[0]

    sub = subdirectory.strip()
    sub_path = Path(sub)

    # 1. If subdirectory is an absolute path or drive path, verify it falls within any allowed root
    if sub_path.is_absolute() or sub.startswith("/") or sub.startswith("\\") or (len(sub) > 1 and sub[1] == ":"):
        candidate = sub_path.resolve()
        for root in resolved_roots:
            if candidate == root or candidate.is_relative_to(root):
                return candidate
        raise UnsafePathError(
            f"Target path '{subdirectory}' is outside all configured allowed roots: {resolved_roots}"
        )

    # 2. If subdirectory is relative, check if its first component selects a non-default root
    parts = sub_path.parts
    if parts:
        first_part = parts[0].lower()
        for root in resolved_roots:
            if root.name.lower() == first_part:
                remainder = Path(*parts[1:]) if len(parts) > 1 else Path(".")
                target = (root / remainder).resolve()
                if target.is_relative_to(root):
                    return target
                raise UnsafePathError(f"Subdirectory '{subdirectory}' attempts to escape allowed root '{root}'.")

    # 3. Default to resolving relative to the primary root (allowed_roots[0])
    primary_root = resolved_roots[0]
    target = (primary_root / sub).resolve()
    if not target.is_relative_to(primary_root):
        raise UnsafePathError(f"Subdirectory '{subdirectory}' attempts to escape the allowed root '{primary_root}'.")

    return target


def validate_headers(
    headers: dict[str, str] | None,
    allow_sensitive: bool = False,
) -> dict[str, str]:
    """
    Validate headers and reject sensitive credentials unless explicitly permitted.
    """
    if not headers:
        return {}

    for key in headers.keys():
        lower_key = key.lower()
        if lower_key in SENSITIVE_HEADERS and not allow_sensitive:
            raise SensitiveHeaderError(
                f"Sensitive header '{key}' is disabled by default. "
                f"Set ABDM_MCP_ALLOW_SENSITIVE_HEADERS=true in environment to allow it."
            )

    return headers
