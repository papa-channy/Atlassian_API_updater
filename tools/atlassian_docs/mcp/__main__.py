import sys

try:
    from . import server
except ImportError as exc:  # mcp SDK missing
    if "mcp" in str(exc):
        print("The MCP layer needs the official SDK: pip install -r requirements-mcp.txt", file=sys.stderr)
        sys.exit(3)
    raise

sys.exit(server.main())
