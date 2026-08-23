#!/usr/bin/env python3
"""Assert the MCP tool surface each client is contracted to receive.

Speaks JSON-RPC to each server over stdio exactly as a coding client would, so a
passing run means the server really starts and really exposes the expected tools.
Requires no credentials, no model calls, and no authenticated session.

Usage:  python3 tests/mcp_contract.py [--skip-search]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "local-code-navigator"

SERENA_PIN = "serena-agent==1.7.0"

# Serena tools that a coding client already provides. Excluding them is the whole
# point of the custom contexts: the client's own tools stay the route for literal
# search and file reading, and Serena is left to answer code-intelligence questions.
CLIENT_OWNED = [
    "create_text_file",
    "read_file",
    "execute_shell_command",
    "find_file",
    "list_dir",
    "search_for_pattern",
]

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f" -- {detail}" if detail else ""))
        failures.append(label)


def mcp_session(cmd: list[str], requests: list[dict], env: dict | None = None,
                cwd: str | None = None, timeout: int = 600) -> dict[int, dict]:
    """Run one stdio MCP session and return replies keyed by request id.

    stdin is deliberately held open until every expected reply arrives. An MCP server
    shuts down on stdin EOF, so closing it up front (as subprocess.run does) kills a
    long tools/call -- such as the first search, which has to build an index -- before
    it can answer.
    """
    lines = [json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "contract-test", "version": "0"}},
    }), json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})]
    lines += [json.dumps(r) for r in requests]
    wanted = {1} | {r["id"] for r in requests}

    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env={**os.environ, **(env or {})}, cwd=cwd,
    )

    watchdog = threading.Timer(timeout, proc.kill)
    watchdog.start()
    replies: dict[int, dict] = {}
    try:
        assert proc.stdin and proc.stdout
        proc.stdin.write("\n".join(lines) + "\n")
        proc.stdin.flush()

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("id") is not None:
                replies[msg["id"]] = msg
                if wanted <= set(replies):
                    break
    finally:
        watchdog.cancel()
        try:
            if proc.stdin:
                proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr = proc.stderr.read() if proc.stderr else ""

    if 1 not in replies:
        tail = "\n".join(stderr.splitlines()[-15:])
        raise RuntimeError(f"server never completed initialize\ncmd: {' '.join(cmd)}\nstderr tail:\n{tail}")
    return replies


def serena_tools(context: str) -> tuple[list[str], str]:
    cmd = [
        "uvx", "--python", "3.12", "--from", SERENA_PIN, "serena", "start-mcp-server",
        "--context", context, "--project", str(PLUGIN),
        "--enable-web-dashboard", "false", "--open-web-dashboard", "false",
    ]
    replies = mcp_session(cmd, [{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    version = replies[1]["result"].get("serverInfo", {}).get("version", "?")
    return sorted(t["name"] for t in replies[2]["result"]["tools"]), version


def test_serena_context(name: str, context_file: Path, expect_replace_content: bool,
                        expect_activate_project: bool) -> None:
    print(f"\n[serena] context: {context_file.name}")
    if not context_file.exists():
        check(f"{name}: context file exists", False, f"missing {context_file}")
        return
    tools, version = serena_tools(str(context_file))
    print(f"  serena app version: {version}  ({SERENA_PIN})")
    print(f"  tool count: {len(tools)}")

    for tool in CLIENT_OWNED:
        check(f"{name}: excludes {tool}", tool not in tools)

    # single_project: true is what removes activate_project. Claude pins the project at
    # startup via ${CLAUDE_PROJECT_DIR} so it is gone there; Codex cannot pin one (its
    # cwd is the plugin root), so the tool must remain for the skill to activate with.
    check(f"{name}: activate_project {'present' if expect_activate_project else 'absent'}",
          ("activate_project" in tools) == expect_activate_project,
          f"tools={tools}")

    # The code-intelligence tools are the reason the plugin exists at all.
    for tool in ("find_symbol", "find_referencing_symbols", "get_symbols_overview",
                 "replace_symbol_body", "rename_symbol"):
        check(f"{name}: provides {tool}", tool in tools, f"tools={tools}")

    check(f"{name}: replace_content {'present' if expect_replace_content else 'absent'}",
          ("replace_content" in tools) == expect_replace_content,
          f"tools={tools}")


def test_semble(run_search: bool) -> None:
    print("\n[semble] launcher: scripts/start_semble.py")
    cache = Path(tempfile.mkdtemp(prefix="lcn-contract-"))
    env = {"HF_HOME": str(cache / "hf"), "SEMBLE_CACHE_LOCATION": str(cache / "semble")}
    cmd = ["uv", "run", "--python", "3.12", "--script", str(PLUGIN / "scripts" / "start_semble.py")]

    requests = [{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    if run_search:
        # A real search is the ONLY thing that reaches LockedIndexCache._build_index.
        # initialize/tools/list alone never builds an index, so a startup-only smoke
        # test would pass while exercising none of this plugin's own code.
        requests.append({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "search",
                       "arguments": {"query": "start the semble mcp server",
                                     "repo": str(PLUGIN), "top_k": 3}},
        })

    try:
        replies = mcp_session(cmd, requests, env=env)
        version = replies[1]["result"].get("serverInfo", {}).get("version", "?")
        print(f"  semble app version: {version}")
        tools = sorted(t["name"] for t in replies[2]["result"]["tools"])
        check("semble: exposes search", "search" in tools, f"tools={tools}")
        check("semble: exposes find_related", "find_related" in tools, f"tools={tools}")

        if run_search:
            got = replies.get(3, {})
            check("semble: search returns a result", "result" in got and not got.get("error"),
                  json.dumps(got)[:300])
            # The lock directory is created inside the patched _build_index. Its
            # existence is positive proof the concurrency patch actually ran.
            locks = cache / "semble" / ".locks"
            check("semble: LockedIndexCache._build_index ran (.locks created)", locks.is_dir(),
                  f"missing {locks}")
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-search", action="store_true",
                        help="skip the Semble index build (faster; leaves the lock path untested)")
    args = parser.parse_args()

    print(f"plugin root: {PLUGIN}")
    contexts = PLUGIN / "contexts"

    # Claude keeps replace_content: its built-in Edit refuses to edit files it believes
    # it has not read, and content read through Serena does not satisfy that check.
    test_serena_context("claude", contexts / "claude-balanced.yml",
                        expect_replace_content=True, expect_activate_project=False)
    test_serena_context("codex", contexts / "codex-balanced.yml",
                        expect_replace_content=True, expect_activate_project=True)

    test_semble(run_search=not args.skip_search)

    print(f"\n{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
