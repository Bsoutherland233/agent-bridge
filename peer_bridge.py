"""Portable bootstrap for local stdio MCP and Grok's approved local commands."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from agent_bridge.peer_mcp import main

if __name__ == '__main__': raise SystemExit(main())
