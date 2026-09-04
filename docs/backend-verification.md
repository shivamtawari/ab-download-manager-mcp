# ABDM Backend Capabilities & Interoperability Verification

Date: September 2026  
Target Environment: Windows (AB Download Manager v1.10.x+)

## Summary of Findings

| Capability Area | Status | Evidence & Notes |
| :--- | :--- | :--- |
| **REST Port & Health** | **VERIFIED** | Listens on port `15151`. `GET /queues` returns `200 OK` with JSON queue array (`[{"id": 0, "name": "Main"}]`). |
| **REST Headless Creation** | **VERIFIED** | `POST /start-headless-download` accepts JSON payload (`downloadSource`, `name`, `folder`, `queueId`) and returns `200 OK` ("OK"). |
| **CLI Binary Presence** | **VERIFIED** | Located at `AppData\Local\ABDownloadManager\ABDownloadManagerCli.exe`. |
| **CLI Download Creation** | **VERIFIED** | `ABDownloadManagerCli.exe download add http ...` returns **integer download ID directly to stdout** (e.g., `17`, `19`). |
| **State Sharing (REST <-> CLI)** | **VERIFIED** | Downloads created via REST (`POST /start-headless-download`) are assigned sequential IDs in the shared database. |
| **CLI Lifecycle Control** | **VERIFIED** | `download show <id>`, `download pause <id>`, `download resume <id>`, and `download remove <id>` successfully inspect and control tasks. |
| **CLI Output Format** | **VERIFIED** | `download show <id>` returns tabular ASCII boxes: `? ID ? Status ? Name ? Folder ?` easily parsed into structured models. |

## Verified Interoperability Test Trace

```text
1. REST Headless Dispatch:
   POST http://127.0.0.1:15151/start-headless-download
   Payload: { "downloadSource": { "link": "..." }, "name": "test_rest_interop.txt", "folder": "...", "queueId": 0 }
   Status: 200 OK

2. CLI State Visibility:
   Command: ABDownloadManagerCli.exe download show 18
   Output:
   ???????????????????????????????????????????????????????????????????????
   ? ID ? Status ? Name                  ? Folder                        ?
   ???????????????????????????????????????????????????????????????????????
   ? 18 ? Paused ? test_rest_interop.txt ? C:\Users\shiva\Downloads\ABDM ?
   ???????????????????????????????????????????????????????????????????????

3. CLI Lifecycle Action:
   Command: ABDownloadManagerCli.exe download resume 18 -> Exit code 0
   Command: ABDownloadManagerCli.exe download remove 18 -> Exit code 0
```

## Architecture Implications

1. **Unified State is Confirmed**: CLI and REST share the exact same active download state.
2. **Dual Dispatch Strategy**:
   - Interactive downloads use REST (`POST /add`) to trigger the desktop confirmation GUI.
   - Headless downloads can use CLI `download add http --start` or REST `/start-headless-download` while retaining full CLI lifecycle control (`pause`, `resume`, `remove`, `show`).
