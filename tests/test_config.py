"""Unit tests for configuration discovery and settings."""

from abdm_mcp.config import load_settings


def test_load_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("ABDM_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ABDM_PORT", raising=False)
    monkeypatch.delenv("ABDM_API_KEY", raising=False)
    monkeypatch.delenv("ABDM_MCP_ALLOWED_DOWNLOAD_ROOTS", raising=False)

    settings = load_settings()
    assert settings.port in (15151, 9554) or settings.port > 0
    assert len(settings.allowed_roots) >= 1
    assert settings.allow_private_networks is False
    assert settings.allow_sensitive_headers is False
    assert settings.allow_file_deletion is False
    assert settings.default_mode == "interactive"


def test_load_settings_custom_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ABDM_PORT", "18888")
    monkeypatch.setenv("ABDM_API_KEY", "my-secret-key")
    monkeypatch.setenv("ABDM_MCP_ALLOW_PRIVATE_NETWORKS", "true")
    monkeypatch.setenv("ABDM_MCP_ALLOW_SENSITIVE_HEADERS", "true")
    monkeypatch.setenv("ABDM_MCP_ALLOW_FILE_DELETION", "true")
    monkeypatch.setenv("ABDM_MCP_DEFAULT_MODE", "headless")
    monkeypatch.setenv("ABDM_MCP_ALLOWED_DOWNLOAD_ROOTS", f"{tmp_path}/a,{tmp_path}/b")

    settings = load_settings()
    assert settings.port == 18888
    assert settings.api_key == "my-secret-key"
    assert settings.allow_private_networks is True
    assert settings.allow_sensitive_headers is True
    assert settings.allow_file_deletion is True
    assert settings.default_mode == "headless"
    assert len(settings.allowed_roots) == 2
