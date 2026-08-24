#!/usr/bin/env python3
"""Assert the routing hook nudges without getting in the way.

The risk this guards is shipping a plugin that quietly disables a user's built-in
tools. `remind` must always allow the call, `block` must only ever trigger on actual
discovery commands, and the MCP_FALLBACK=1 escape hatch must work.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

HOOK = (Path(__file__).resolve().parent.parent / "plugins" / "local-code-navigator"
        / "hooks" / "routing_reminder.py")

SEARCH_CMD = "gr" + "ep -r foo ."
FALLBACK_CMD = "MCP_FALLBACK=1 " + SEARCH_CMD

failures: list[str] = []


def run(tool: str, mode: str, command: str = "", session: str | None = None) -> tuple[int, str]:
    payload = {"tool_name": tool, "tool_input": {"command": command} if command else {},
               "session_id": session or str(uuid.uuid4())}
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True,
                          env={"LCN_ROUTING_HOOK": mode, "PATH": "/usr/bin:/bin"})
    return proc.returncode, proc.stdout


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f" -- {detail}"))
    if not ok:
        failures.append(label)


def main() -> int:
    print("[remind mode: must never block]")
    for tool, cmd in (("Grep", ""), ("Glob", ""), ("Bash", SEARCH_CMD)):
        code, out = run(tool, "remind", cmd)
        check(f"remind allows {tool}{' ' + cmd if cmd else ''}", code == 0, f"exit {code}")
    # A fresh id per invocation: the hook marks "already reminded" with a file in the
    # temp dir, so a fixed id passes on a clean machine and fails on the second run.
    session = f"contract-{uuid.uuid4()}"
    code, out = run("Grep", "remind", session=session)
    check("remind prints guidance on first call", "local-code-navigator" in out, repr(out[:80]))
    code, out = run("Grep", "remind", session=session)
    check("remind stays quiet on the second call in a session", out.strip() == "", repr(out[:80]))

    print("\n[off mode: must be completely silent]")
    code, out = run("Grep", "off")
    check("off allows and prints nothing", code == 0 and out.strip() == "", f"exit {code} out {out!r}")

    print("\n[block mode: opt-in enforcement]")
    code, out = run("Grep", "block")
    check("block refuses Grep", code == 2, f"exit {code}")
    code, out = run("Bash", "block", SEARCH_CMD)
    check("block refuses shell search", code == 2, f"exit {code}")
    code, out = run("Bash", "block", FALLBACK_CMD)
    check("block honors the MCP_FALLBACK=1 escape hatch", code == 0, f"exit {code}")

    print("\n[block mode must not overreach]")
    for cmd in ("ls -la", "python3 -c 'print(1)'", "git status",
                "echo searching is a word"):
        code, out = run("Bash", "block", cmd)
        check(f"block allows: {cmd}", code == 0, f"exit {code} out {out!r}")

    print("\n[malformed input must never break a session]")
    proc = subprocess.run([sys.executable, str(HOOK)], input="not json",
                          capture_output=True, text=True,
                          env={"LCN_ROUTING_HOOK": "block", "PATH": "/usr/bin:/bin"})
    check("garbage stdin allows the call", proc.returncode == 0, f"exit {proc.returncode}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nrouting hook contract intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
