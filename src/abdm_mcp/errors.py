"""Standardized exception taxonomy for AB Download Manager MCP Server."""

class ABDMError(Exception):
    """Base exception for all ABDM MCP operations."""
    pass


class ABDMUnavailableError(ABDMError):
    """Raised when the AB Download Manager desktop application is not reachable."""
    pass


class ABDMAuthenticationError(ABDMError):
    """Raised when the API key is missing, rejected, or unauthorized."""
    pass


class UnsupportedParameterError(ABDMError):
    """Raised when a parameter is supplied that cannot be accepted in the given mode."""
    pass


class UnsafePathError(ABDMError):
    """Raised when a path escapes the allowed download sandboxes."""
    pass


class UnsafeFilenameError(ABDMError):
    """Raised when a filename contains path traversal sequences or illegal characters."""
    pass


class UnsafeURLError(ABDMError):
    """Raised when a URL scheme or target IP violates security policy (e.g. SSRF guard)."""
    pass


class SensitiveHeaderError(ABDMError):
    """Raised when sensitive headers (Cookie, Authorization) are sent without explicit opt-in."""
    pass


class DownloadNotFoundError(ABDMError):
    """Raised when the requested download task ID does not exist."""
    pass


class CLIUnavailableError(ABDMError):
    """Raised when the AB Download Manager CLI executable cannot be found or executed."""
    pass


class CLITimeoutError(ABDMError):
    """Raised when a CLI command exceeds the allowed execution time."""
    pass


class CLIOutputLimitError(ABDMError):
    """Raised when CLI stdout or stderr output exceeds the maximum allowed buffer size."""
    pass


class BackendCompatibilityError(ABDMError):
    """Raised when an operation is requested that the current backend configuration does not support."""
    pass
