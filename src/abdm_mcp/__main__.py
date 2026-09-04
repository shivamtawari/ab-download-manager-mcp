"""Entrypoint for running the AB Download Manager MCP server via CLI."""

from abdm_mcp.server import create_server


def main():
    """Main execution function starting the stdio MCP server."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
