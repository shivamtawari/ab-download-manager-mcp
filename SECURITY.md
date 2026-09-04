# Security Policy

## Reporting Security Issues

If you discover a potential security vulnerability in `abdm-mcp`, please do not open a public issue. Instead, report it privately via GitHub Security Advisories or by emailing the maintainer.

## Security Architecture & Design Guardrails

`abdm-mcp` is designed to be invoked by autonomous AI coding agents (Claude, Cursor, Antigravity). To prevent malicious or unintended agent actions, the server implements strict security boundaries:

1. **Path Sandboxing**: By default, headless downloads are strictly restricted to `~/Downloads/ABDM`. Arbitrary destination paths outside configured roots are rejected.
2. **Private-Network URL Guard**: Direct connections to `localhost`, loopback (`127.0.0.0/8`, `::1`), RFC1918 private IP subnets, and cloud link-local metadata endpoints (`169.254.169.254`) are blocked by default.
3. **Filename Sanitization**: Path traversal sequences (`..`), slashes, drive letters, control characters, and reserved Windows device names (`CON`, `PRN`, `AUX`, `NUL`, etc.) are rejected.
4. **Header Protection**: Sensitive headers (`Cookie`, `Authorization`, `Proxy-Authorization`, `Host`) are blocked by default to prevent credential exfiltration.
5. **Deletion Protection**: File deletion on task cancellation is disabled by default (`ABDM_MCP_ALLOW_FILE_DELETION=false`). When enabled, the file target is verified to reside strictly inside the allowed download sandbox before deletion.
