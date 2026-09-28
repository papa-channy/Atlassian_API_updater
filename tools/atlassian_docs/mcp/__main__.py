import sys

try:
    from . import server
except ImportError as exc:  # mcp SDK missing
    if exc.name == "mcp" or (exc.name or "").startswith("mcp."):
        print("The MCP layer needs the official SDK: pip install -r requirements-mcp.txt", file=sys.stderr)
        sys.exit(3)
    raise

sys.exit(server.main())
