# Implementation Plan: Production-Grade AB Download Manager MCP Server (`abdm-mcp`)

**Project Directory:** `D:\Projects\ab-download-manager-mcp`  
**Status:** Implementation-Ready — Beginning Phase 1 Verification

An open-source Model Context Protocol (MCP) server connecting AI coding assistants and autonomous agents (Antigravity, Claude Desktop, Cursor, etc.) to **AB Download Manager (ABDM)**.

---

## Final Architecture Refinements

```
  Claude / Cursor / Agent
            │
            │ MCP stdio (Typed Pydantic Output Schemas)
            ▼
┌───────────────────────────────┐
│     mcp.server.MCPServer      │ (server.py - Official MCP Python SDK v2)
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│          ABDMService          │ (service.py - Orchestration & Capability router)
└───────┬───────────────┬───────┘
        │               │
        ▼               ▼
┌──────────────┐ ┌──────────────┐
│ RestBackend  │ │  CliBackend  │
└───────┬──────┘ └──────┬───────┘
        │               │
        │ HTTP :15151   │ asyncio.create_subprocess_exec (NO shell)
        │ X-API-Key     │
        └───────┬───────┘
                ▼
      [ AB Download Manager ]
```

### 1. Schema & Parameter Corrections
* **`queue_id: int | None = None`**: Strongly typed integer matching ABDM's OpenAPI `/queues` and `/start-headless-download`.
* **Interactive vs. Headless Disparity**:
  * `mode="interactive"`: Takes `url`, `headers`, `download_page`. Rejects `filename`, `subdirectory`, or `queue_id` with `UnsupportedParameterError` (prevents agents from assuming preselected paths when user GUI confirmation is displayed).
  * `mode="headless"`: Takes `url`, `filename`, `subdirectory`, `queue_id`, `headers`.

### 2. Comprehensive Security Guardrails (`security.py`)
* **Filename Validation (`UnsafeFilenameError`)**:
  * Reject slashes (`/`, `\`), relative sequences (`..`), drive letters (`C:`), UNC paths (`\\server\share`), NUL/control bytes, and Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`).
* **Path Sandboxing (`UnsafePathError`)**:
  * Default allowed root: strictly `~/Downloads/ABDM` (customizable via `ABDM_MCP_ALLOWED_DOWNLOAD_ROOTS`).
  * Enforce canonical path resolution: `target = (root / subdirectory).resolve()`; assert `target.is_relative_to(root.resolve())`.
* **Private-Network URL Guard / SSRF Risk Reduction (`UnsafeURLError`)**:
  * Best-effort pre-dispatch blocking of `localhost`, `127.0.0.0/8`, `::1`, RFC1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and link-local (`169.254.169.254`).
  * Documented limitation: Cannot guarantee immunity against DNS-rebinding or 302 redirects executed downstream by ABDM.
* **Sensitive Header Protection (`SensitiveHeaderError`)**:
  * Reject `Cookie`, `Authorization`, `Proxy-Authorization`, and `Host` unless explicitly enabled via `ABDM_MCP_ALLOW_SENSITIVE_HEADERS=true`.
* **Safe Deletion**:
  * `abdm_remove(download_id, delete_file=True)` disabled by default (`ABDM_MCP_ALLOW_FILE_DELETION=false`). When enabled, verifies file target lies inside allowed sandbox roots before deletion.

### 3. Safe Subprocess Execution (`backends/cli.py`)
* Strictly invoke `asyncio.create_subprocess_exec(cli_path, *args)` — **never** `shell=True` / `create_subprocess_shell`.
* Enforce hard execution timeouts (default 10s) and stdout/stderr buffer caps (1MB) to prevent memory exhaustion.

### 4. Typed Pydantic Tool Outputs
Tools return validated Pydantic models with derived JSON Schemas:
* `DownloadSubmission`: `{ accepted: bool, backend: "rest" | "cli", download_id: str | None, mode: str, message: str | None }`
* `BatchSubmission`: `{ submitted: int, failed: int, items: list[DownloadSubmission] }`
* `ActionResult`: `{ success: bool, download_id: str, action: str, message: str | None }`
* `HealthReport`: `{ rest_available: bool, authenticated: bool | None, cli_available: bool, cli_version: str | None, shared_state_verified: bool, capabilities: list[str] }`
* `QueueInfo`: `{ id: int, name: str }`

---

## Tool Surface with MCP Annotations

| Tool Name | Parameters | MCP Annotations | Description |
| :--- | :--- | :--- | :--- |
| `abdm_download` | `url: str`, `mode: "interactive" \| "headless" = "interactive"`, `filename?: str`, `subdirectory?: str`, `queue_id?: int`, `headers?: dict` | `openWorldHint=True` | Submits a download. Fails fast if path/queue parameters are given to interactive mode. |
| `abdm_download_batch` | `urls: list[str]`, `mode: "interactive" \| "headless" = "interactive"`, `queue_id?: int` | `openWorldHint=True` | Enqueues up to 50 URLs with partial success tracking. |
| `abdm_get_queues` | *none* | `readOnlyHint=True` | Returns list of configured queues (`id: int`, `name: str`). |
| `abdm_check_status` | *none* | `readOnlyHint=True` | Health probe: REST reachability, auth status, CLI presence, capabilities. |
| `abdm_list_downloads` | `status?: "active" \| "completed" \| "failed" \| "all"` | `readOnlyHint=True` | Lists current downloads (conditional on CLI support). |
| `abdm_get_download` | `download_id: str` | `readOnlyHint=True` | Returns task details for a single download. |
| `abdm_pause` | `download_id: str` | `idempotentHint=True` | Pauses an active download. |
| `abdm_resume` | `download_id: str` | `idempotentHint=True` | Resumes a paused download. |
| `abdm_remove` | `download_id: str`, `delete_file: bool = False` | `destructiveHint=True` | Cancels/removes a task (file deletion requires opt-in & sandbox verification). |

---

## Step-by-Step Implementation Roadmap & Git Commit Strategy

We will make **atomic, clean commits** at each milestone for a clean GitHub history:

1. **Commit 1: Repository Scaffold & Documentation**
   - Initialize Git repository in `D:\Projects\ab-download-manager-mcp`.
   - Add `.gitignore`, `pyproject.toml` (hatchling backend, dependencies: `mcp>=2,<3`, `httpx>=0.28`, `pydantic>=2`, dev: `pytest`, `pytest-asyncio`, `respx`, `ruff`, `mypy`).
   - Add `LICENSE` (MIT), `IMPLEMENTATION_PLAN.md`, `SECURITY.md`, `CONTRIBUTING.md`.

2. **Commit 2: Phase 1 Live Verification Experiments**
   - Test A: Verify expected `X-API-Key: <key>` against local port `15151` on `GET /queues`.
   - Test B: Probe `ABDownloadManagerCli` on local system for command syntax and JSON output.
   - Test C: Directional test: REST headless creation $\rightarrow$ CLI list visibility.
   - Record findings in `src/abdm_mcp/models.py` (`Capabilities`).

3. **Commit 3: Foundation, Security & Config Modules**
   - Implement `errors.py` (complete error taxonomy).
   - Implement `security.py` (canonical path resolution, filename validation, private-network guard, header checks).
   - Implement `config.py` (reads `~/.abdm`, `app.port`, API key, env vars).
   - Add comprehensive unit tests in `tests/test_security.py` and `tests/test_config.py`.

4. **Commit 4: Backends Implementation**
   - Implement `backends/base.py` interface.
   - Implement `backends/rest.py` (async `httpx` with `X-API-Key`, `/queues`, `/add`, `/start-headless-download`).
   - Implement `backends/cli.py` (safe `asyncio.create_subprocess_exec` with timeouts and caps).
   - Add unit tests with `respx` in `tests/test_rest_backend.py`.

5. **Commit 5: Service Layer & MCP Server**
   - Implement `service.py` (`ABDMService` coordinator, parameter disparity validation, batch slicing $\le 50$).
   - Implement `server.py` (`MCPServer` with annotations and typed Pydantic outputs).
   - Implement `__main__.py` CLI runner.
   - Add unit tests in `tests/test_service.py`.

6. **Commit 6: Integration Tests, CI & Final Polish**
   - Add `.github/workflows/ci.yml`.
   - Finalize `README.md` with installation guides (`uvx abdm-mcp`, Claude Desktop, Cursor, Antigravity).
   - Run full test suite (`pytest`) and linting (`ruff`).
