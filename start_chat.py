"""Portable entry point; works without setting PYTHONPATH."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from agent_bridge.chat.__main__ import main

if __name__ == '__main__':
    raise SystemExit(main())
