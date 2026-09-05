# AB Download Manager MCP Server (`abdm-mcp`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Specification](https://img.shields.io/badge/MCP-2.0+-green.svg)](https://modelcontextprotocol.io/)
[![CI](https://github.com/shivamtawari/ab-download-manager-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/shivamtawari/ab-download-manager-mcp/actions)

A production-grade Model Context Protocol (MCP) server that connects AI coding assistants and autonomous agents ([Claude Desktop](https://claude.ai/download), [Cursor](https://cursor.com), [Antigravity](https://github.com/google/antigravity)) to [AB Download Manager (ABDM)](https://abdownloadmanager.com).

Offload large file downloads (game installers, AI model weights, dataset archives, video collections) from your agent sessions to AB Download Manager with multi-threaded segment acceleration (8–32 connections), pause/resume, and queueing.

---

## Quick Start

### Run with `uvx` (No installation needed)

```bash
uvx abdm-mcp
```

### Install with `pip`

```bash
pip install abdm-mcp
python -m abdm_mcp
```

---

## Agent Configuration

### 1. Claude Desktop
Add to your `claude_desktop_config.json`:
* **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
* **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "abdm": {
      "command": "uvx",
      "args": ["abdm-mcp"],
      "env": {
        "ABDM_MCP_DEFAULT_MODE": "interactive",
        "ABDM_API_KEY": "your_api_key_if_configured"
      }
    }
  }
}
```

### 2. Cursor
Add to your `.cursor/mcp.json` or Global MCP settings:

```json
{
  "mcpServers": {
    "abdm": {
      "command": "uvx",
      "args": ["abdm-mcp"]
    }
  }
}
```

---

## Tool Surface & Capabilities

All tools return strongly-typed Pydantic schemas and include explicit MCP Tool Annotations:

| Tool Name | Parameters | MCP Annotations | Description |
| :--- | :--- | :--- | :--- |
| `abdm_download` | `url` (str)<br>`mode` ("interactive" \| "headless")<br>`filename` (str, optional)<br>`subdirectory` (str, optional)<br>`queue_id` (int, optional)<br>`headers` (dict, optional)<br>`download_page` (str, optional) | `openWorldHint=True`<br>`destructiveHint=False` | Submits a download. Fails fast with `UnsupportedParameterError` if path/queue options are supplied in interactive mode. |
| `abdm_download_batch` | `urls` (list[str])<br>`mode` ("interactive" \| "headless")<br>`queue_id` (int, optional) | `openWorldHint=True`<br>`destructiveHint=False` | Enqueues up to 50 URLs in a batch with partial success tracking. |
| `abdm_get_queues` | *none* | `readOnlyHint=True` | Fetches configured download queues from ABDM. |
| `abdm_check_status` | *none* | `readOnlyHint=True` | Probes REST reachability, authentication, CLI status, and active capabilities. |
| `abdm_list_downloads` | `status` ("active" \| "paused" \| "completed" \| "error" \| "all") | `readOnlyHint=True` | Lists current downloads reported by ABDM. |
| `abdm_get_download` | `download_id` (str) | `readOnlyHint=True` | Returns status and metadata for a single download task by ID. |
| `abdm_pause` | `download_id` (str) | `idempotentHint=True`<br>`destructiveHint=False` | Pauses an active download task. |
| `abdm_resume` | `download_id` (str) | `idempotentHint=True`<br>`destructiveHint=False` | Resumes a paused download task. |
| `abdm_remove` | `download_id` (str)<br>`delete_file` (bool = False) | `destructiveHint=True` | Cancels and removes a download task. File deletion requires policy opt-in and path verification. |

---

## Security & Sandboxing Guardrails

Autonomous agents are powerful, but should not have unrestricted filesystem or network write access. `abdm-mcp` implements defense-in-depth:

1. **Path Sandboxing**: By default, headless downloads are strictly confined to `~/Downloads/ABDM`. Path traversal escapes (`../`) and absolute paths outside allowed roots are rejected.
2. **Private-Network URL Guard**: Protects against SSRF by rejecting direct requests to `localhost`, `127.0.0.0/8`, `::1`, RFC1918 LAN subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and link-local metadata endpoints (`169.254.169.254`).
3. **Filename Sanitization**: Rejects slashes, drive prefixes, control characters, and reserved Windows device names (`CON`, `PRN`, `AUX`, `NUL`, etc.).
4. **Header Protection**: Blocks sensitive headers (`Cookie`, `Authorization`, `Proxy-Authorization`, `Host`) by default to prevent credential leakage.
5. **Safe Subprocess Execution**: The CLI backend strictly uses `asyncio.create_subprocess_exec` (never `shell=True`) with bounded streaming readers (1MB limit) and hard execution timeouts.

### Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ABDM_CONFIG_DIR` | `~/.abdm` | Custom or portable configuration directory path. |
| `ABDM_PORT` | `15151` | Port of the ABDM local integration server (auto-discovered from `appSettings.json`). |
| `ABDM_API_KEY` | *None* | Optional authentication key configured in ABDM. |
| `ABDM_CLI_PATH` | Auto-detected | Explicit path to `ABDownloadManagerCli` executable. |
| `ABDM_MCP_DEFAULT_MODE` | `interactive` | Default mode: `interactive` (GUI confirmation) or `headless` (silent background). |
| `ABDM_MCP_ALLOWED_DOWNLOAD_ROOTS` | `~/Downloads/ABDM` | Comma-separated list of allowed download directories. |
| `ABDM_MCP_ALLOW_PRIVATE_NETWORKS` | `false` | Set to `true` to allow downloads from LAN / private IPs. |
| `ABDM_MCP_ALLOW_SENSITIVE_HEADERS` | `false` | Set to `true` to allow `Cookie` and `Authorization` headers. |
| `ABDM_MCP_ALLOW_FILE_DELETION` | `false` | Set to `true` to permit `abdm_remove(delete_file=True)`. |
| `ABDM_MCP_MAX_BATCH_SIZE` | `50` | Maximum URLs accepted in a single `abdm_download_batch` call. |

---

## Development & Testing

```bash
# Clone the repository
git clone https://github.com/shivamtawari/ab-download-manager-mcp.git
cd ab-download-manager-mcp

# Install dependencies with uv
uv sync --all-groups

# Run full test suite
uv run pytest tests/

# Run linting
uv run ruff check .
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
