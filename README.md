# AB Download Manager MCP Server (`abdm-mcp`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Specification](https://img.shields.io/badge/MCP-2.0+-green.svg)](https://modelcontextprotocol.io/)

A production-oriented Model Context Protocol (MCP) server that connects AI coding assistants and autonomous agents ([Claude Desktop](https://claude.ai/download), [Cursor](https://cursor.com), [Antigravity](https://github.com/google/antigravity)) to [AB Download Manager](https://abdownloadmanager.com).

Offload large file downloads (game installers, AI model weights, dataset archives, videos) from your agent sessions to AB Download Manager with multi-threaded segment acceleration, pause/resume, and queueing.

## Quick Start

### Running with `uvx` (No installation needed)

```bash
uvx abdm-mcp
```

### Configuration in Claude Desktop / Cursor / Antigravity

Add the following to your MCP configuration file (`claude_desktop_config.json` or `mcp.json`):

```json
{
  "mcpServers": {
    "abdm": {
      "command": "uvx",
      "args": ["abdm-mcp"],
      "env": {
        "ABDM_API_KEY": "your_api_key_if_configured",
        "ABDM_MCP_DEFAULT_MODE": "interactive"
      }
    }
  }
}
```

## Features & Architecture

* **Dual Backend Support**: Communicates via official ABDM REST integration (`/add`, `/start-headless-download`, `/queues`) and the ABDM CLI (`list`, `info`, `pause`, `resume`, `remove`).
* **Interactive & Headless Modes**:
  * `mode="interactive"` (Default): Launches ABDM's native confirmation dialog—keeping the human in the loop for large downloads.
  * `mode="headless"`: Fully autonomous background download into a sandboxed destination directory.
* **Agent Defense & Sandboxing**:
  * **Path Sandboxing**: Restricts downloads strictly to configured allowed directories (default: `~/Downloads/ABDM`).
  * **Private-Network Guard**: Protects against SSRF by rejecting direct loopback, LAN, and link-local destinations.
  * **Filename Sanitization**: Rejects path traversal, drive prefixes, and reserved device names.
  * **Sensitive Header Guard**: Protects cookies and authorization tokens from leaking.
