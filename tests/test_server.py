"""Unit tests for FastMCP server instantiation and tool annotations."""

from abdm_mcp.server import create_server


def test_server_creation_and_tools():
    mcp = create_server()
    assert mcp.name == "AB Download Manager"
    
    # Check registered tools
    tools = mcp._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "abdm_download",
        "abdm_download_batch",
        "abdm_get_queues",
        "abdm_check_status",
        "abdm_list_downloads",
        "abdm_get_download",
        "abdm_pause",
        "abdm_resume",
        "abdm_remove",
    }
    assert expected.issubset(tool_names)


def test_tool_annotations():
    mcp = create_server()
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    
    # Check read-only hint on status
    status_tool = tools["abdm_check_status"]
    assert status_tool.annotations.readOnlyHint is True
    assert status_tool.annotations.destructiveHint is False

    # Check destructive hint on remove
    remove_tool = tools["abdm_remove"]
    assert remove_tool.annotations.destructiveHint is True


def test_configured_default_mode(tmp_path):
    from abdm_mcp.config import Settings

    settings = Settings(
        config_dir=tmp_path,
        allowed_roots=[tmp_path],
        default_mode="headless",
    )
    mcp = create_server(settings=settings)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}

    # Verify abdm_download has default "headless"
    dl_schema = tools["abdm_download"].parameters
    assert dl_schema["properties"]["mode"]["default"] == "headless"

    # Verify abdm_download_batch has default "headless"
    batch_schema = tools["abdm_download_batch"].parameters
    assert batch_schema["properties"]["mode"]["default"] == "headless"
