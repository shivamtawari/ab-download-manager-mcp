"""Entrypoint for running the AB Download Manager MCP server via CLI."""

import argparse
from typing import Literal

from abdm_mcp.server import create_server


def main() -> None:
    """Main execution function starting the MCP server."""
    parser = argparse.ArgumentParser(
        prog="abdm-mcp",
        description="Model Context Protocol (MCP) server for AB Download Manager",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport protocol: stdio (default), sse, or streamable-http",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address when using network transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on when using network transports (default: 8000)",
    )
    args = parser.parse_args()

    server = create_server(host=args.host, port=args.port)
    transport: Literal["stdio", "sse", "streamable-http"] = args.transport
    server.run(transport=transport)


if __name__ == "__main__":
    main()
