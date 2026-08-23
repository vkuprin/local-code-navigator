#!/usr/bin/env python3
"""PreToolUse nudge toward the routed MCP tools, off the critical path by default.

Three modes, selected by LCN_ROUTING_HOOK:

  remind (default)  On the first discovery-tool call of a session, print a short
                    routing reminder and allow the call. Silent afterwards.
  off               Do nothing at all.
  block             Refuse Grep/Glob and shell grep/find, the way a maintainer who
                    has already decided might want. Opt-in only.

`block` is deliberately not the default. A plugin that disables a user's built-in
tools the moment it is installed breaks legitimate work -- reading a lockfile, grepping
a log -- and the routing argument does not apply to any of that. `remind` states the
preference once and gets out of the way.

Escape hatch in block mode is a MCP_FALLBACK=1 prefix on the Bash command, matching the
convention this project already documents.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

MODE = os.environ.get("LCN_ROUTING_HOOK", "remind").strip().lower()

REMINDER = (
    "local-code-navigator: for code discovery, Semble `search` finds behavior by "
    "meaning and Serena resolves symbols and real references. Built-in search stays "
    "correct for literal text and for reading a file you can already name. "
    "(Set LCN_ROUTING_HOOK=off to silence this, or =block to enforce it.)"
)

SHELL_SEARCH = re.compile(
    r"(^|[;&|()\s])(command\s+)?(rg|grep|fd|find)(\s|$)"
)


def already_reminded(session_id: str) -> bool:
    """One reminder per session. Absent a session id, stay silent rather than nag."""
    if not session_id:
        return True
    marker = Path(tempfile.gettempdir()) / f"lcn-routing-hook-{session_id}"
    if marker.exists():
        return True
    try:
        marker.touch()
    except OSError:
        return True
    return False


def main() -> int:
    if MODE == "off":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    session_id = str(payload.get("session_id") or "")

    is_discovery = tool in ("Grep", "Glob")
    if tool == "Bash":
        command = str(tool_input.get("command") or "")
        if re.match(r"^\s*MCP_FALLBACK=1(\s|$)", command):
            return 0
        is_discovery = bool(SHELL_SEARCH.search(command))

    if not is_discovery:
        return 0

    if MODE == "block":
        print("BLOCKED by local-code-navigator (LCN_ROUTING_HOOK=block).")
        print("Route discovery through Semble search or Serena symbol tools first.")
        print("If the routed tool failed or stayed weak, retry the shell command with a")
        print("MCP_FALLBACK=1 prefix.")
        return 2

    if not already_reminded(session_id):
        print(REMINDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
