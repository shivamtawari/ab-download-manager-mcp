# Contributing to AB Download Manager MCP Server

Thank you for your interest in contributing to `abdm-mcp`!

## Development Setup

This project uses `uv` for fast, reproducible Python environment management:

```bash
# Clone the repository
git clone https://github.com/shivamtawari/ab-download-manager-mcp.git
cd ab-download-manager-mcp

# Install dependencies in a virtual environment
uv sync --all-groups

# Run tests
uv run pytest

# Run linting and formatting checks
uv run ruff check .
```

## Pull Request Guidelines

1. **Safety First**: Never bypass or weaken the path sandboxing or URL security guardrails in `src/abdm_mcp/security.py`.
2. **Subprocess Safety**: Never invoke the shell (`shell=True`) when executing ABDM CLI commands; always use `asyncio.create_subprocess_exec`.
3. **Tests**: Add unit tests in `tests/` for any new tool, parameter, or validation logic.
4. **Error Taxonomy**: Use existing domain exceptions from `errors.py` or extend `ABDMError`.
