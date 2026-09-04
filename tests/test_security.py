"""Unit tests for security guards and sandboxing."""

from pathlib import Path

import pytest

from abdm_mcp.errors import (
    SensitiveHeaderError,
    UnsafeFilenameError,
    UnsafePathError,
    UnsafeURLError,
)
from abdm_mcp.security import (
    resolve_download_path,
    validate_filename,
    validate_headers,
    validate_url,
)


def test_validate_url_valid():
    assert validate_url("https://example.com/file.zip") == "https://example.com/file.zip"
    assert validate_url("http://example.com:8080/data") == "http://example.com:8080/data"


def test_validate_url_schemes():
    with pytest.raises(UnsafeURLError, match="Unsupported URL scheme"):
        validate_url("ftp://example.com/file.zip")
    with pytest.raises(UnsafeURLError, match="Unsupported URL scheme"):
        validate_url("file:///C:/Windows/System32")


def test_validate_url_ssrf_loopback():
    with pytest.raises(UnsafeURLError, match="localhost/loopback"):
        validate_url("http://localhost/admin")
    with pytest.raises(UnsafeURLError, match="localhost/loopback"):
        validate_url("http://127.0.0.1:15151/data")
    with pytest.raises(UnsafeURLError, match="restricted range"):
        validate_url("http://192.168.1.1/setup")
    with pytest.raises(UnsafeURLError, match="restricted range"):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_validate_url_private_opt_in():
    url = "http://127.0.0.1:15151/test"
    assert validate_url(url, allow_private_networks=True) == url


def test_validate_filename_valid():
    assert validate_filename("archive.zip") == "archive.zip"
    assert validate_filename("model..v2.safetensors") == "model..v2.safetensors"
    assert validate_filename("my-file_123.tar.gz") == "my-file_123.tar.gz"
    assert validate_filename(None) is None


def test_validate_filename_traversal():
    with pytest.raises(UnsafeFilenameError):
        validate_filename("..")
    with pytest.raises(UnsafeFilenameError):
        validate_filename(".")
    with pytest.raises(UnsafeFilenameError):
        validate_filename("folder/file.zip")
    with pytest.raises(UnsafeFilenameError):
        validate_filename("..\\file.zip")
    with pytest.raises(UnsafeFilenameError):
        validate_filename("C:file.zip")


def test_validate_filename_windows_reserved():
    for name in ["CON", "prn", "aux.txt", "nul.tar", "COM1", "lpt9.dat"]:
        with pytest.raises(UnsafeFilenameError, match="reserved device name"):
            validate_filename(name)


def test_resolve_download_path():
    root = Path("/tmp/downloads").resolve()
    assert resolve_download_path([root], None) == root
    assert resolve_download_path([root], "models") == (root / "models").resolve()
    assert resolve_download_path([root], "models/sub") == (root / "models/sub").resolve()

    # Traversal escapes
    with pytest.raises(UnsafePathError):
        resolve_download_path([root], "../escape")
    with pytest.raises(UnsafePathError):
        resolve_download_path([root], "/absolute/path")


def test_validate_headers():
    safe = {"User-Agent": "MyAgent", "Accept": "*/*"}
    assert validate_headers(safe) == safe

    for header in ["Cookie", "authorization", "Proxy-Authorization", "Host"]:
        with pytest.raises(SensitiveHeaderError):
            validate_headers({header: "secret"})

    # With opt-in
    assert validate_headers({"Cookie": "session=123"}, allow_sensitive=True) == {"Cookie": "session=123"}
