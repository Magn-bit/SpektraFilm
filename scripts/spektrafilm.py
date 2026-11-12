"""Explicit source-tree entry for the independent local CLI and stdio MCP."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from desktop.automation import main

if __name__=='__main__':raise SystemExit(main())
