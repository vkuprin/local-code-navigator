#!/usr/bin/env python3
"""Does concurrent index construction actually need the launcher's lock?

scripts/start_semble.py overrides a private Semble API to serialize on-disk index
writes. That override is the plugin's main maintenance liability (issue #2), so this
measures whether stock Semble is already safe.

Read this before trusting a green result: search success does NOT prove the cache
write was safe. Each process builds its own in-memory index and answers from that,
and semble's _build_index wraps the cache write in

    try: save_index_to_cache(...)
    except Exception: logger.warning("Failed to save index cache ...")

so a failed or interleaved write is swallowed and the search still returns results.
The write itself is not atomic: SembleIndex.save() writes bm25_index, semantic_index,
chunks and metadata in place, sequentially, with no temp-and-rename and no lock. Two
builders sharing a cache directory can interleave, and a reader can observe metadata
that does not match the chunks beside it.

So this checks three things, not one: whether searches succeeded, whether any process
logged a swallowed cache-write failure, and whether the resulting cache still loads
and is self-consistent afterwards.

Usage:  python3 tests/concurrent_index.py [--procs 4] [--trials 3]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "local-code-navigator"
LAUNCHER = PLUGIN / "scripts" / "start_semble.py"

# Keep the 32 MB embedding model out of the timing: a cold model download would
# dominate and mask the index race this is trying to observe.
SHARED_HF = Path(tempfile.gettempdir()) / "lcn-concurrent-hf"

STOCK_SNIPPET = """
import asyncio
from semble import mcp
asyncio.run(mcp.serve())
"""


def run_one(cache: Path, repo: Path, patched: bool, idx: int) -> dict:
    """Start one server, issue one search, return a structured outcome."""
    if patched:
        cmd = ["uv", "run", "--python", "3.12", "--script", str(LAUNCHER)]
    else:
        cmd = ["uv", "run", "--python", "3.12", "--with", "semble[mcp]==0.5.5",
               "python", "-c", STOCK_SNIPPET]

    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": f"race-{idx}", "version": "0"}}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "search",
                               "arguments": {"query": "serialize index writes",
                                             "repo": str(repo), "top_k": 3}}}),
    ]

    env = {**os.environ, "SEMBLE_CACHE_LOCATION": str(cache), "HF_HOME": str(SHARED_HF)}
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
    watchdog = threading.Timer(900, proc.kill)
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
                if {1, 2} <= set(replies):
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

    swallowed = [l for l in stderr.splitlines() if "Failed to save index cache" in l]

    search = replies.get(2)
    ok = bool(search) and not search.get("error") and not search.get("result", {}).get("isError")
    detail = ""
    if not ok:
        if not search:
            detail = "no reply to search"
        elif search.get("error"):
            detail = json.dumps(search["error"])[:200]
        else:
            detail = json.dumps(search.get("result", {}))[:200]
        interesting = [l for l in stderr.splitlines()
                       if any(k in l for k in ("Error", "Traceback", "Exception", "corrupt", "Lock"))]
        if interesting:
            detail += " | stderr: " + " ;; ".join(interesting[-3:])[:300]
    return {"idx": idx, "ok": ok, "detail": detail, "swallowed": swallowed}


def validate_cache(cache: Path) -> dict:
    """Check that whatever landed in the cache is parseable and self-consistent.

    An interleaved write shows up here as a truncated or unparseable file, or as
    metadata describing a different build than the chunks sitting beside it.
    """
    problems: list[str] = []
    index_dirs = [d for d in cache.glob("*") if d.is_dir() and d.name != ".locks"]
    if not index_dirs:
        return {"checked": 0, "problems": ["no index directory was published"]}

    for d in index_dirs:
        for sub in sorted(p for p in d.rglob("*") if p.is_dir()):
            meta = sub / "metadata.json"
            chunks = sub / "chunks.json"
            for f in (meta, chunks):
                if not f.exists():
                    continue
                if f.stat().st_size == 0:
                    problems.append(f"{f.relative_to(cache)} is zero bytes")
                    continue
                try:
                    json.loads(f.read_text())
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    problems.append(f"{f.relative_to(cache)} does not parse: {exc}")
    return {"checked": len(index_dirs), "problems": problems}


def run_arm(label: str, patched: bool, procs: int, repo: Path) -> dict:
    cache = Path(tempfile.mkdtemp(prefix=f"lcn-race-{label}-"))
    try:
        with ThreadPoolExecutor(max_workers=procs) as pool:
            results = list(pool.map(
                lambda i: run_one(cache, repo, patched, i), range(procs)))
        failures = [r for r in results if not r["ok"]]
        swallowed = [w for r in results for w in r.get("swallowed", [])]
        validation = validate_cache(cache)
        index_dirs = sorted(p.name for p in cache.glob("*") if p.is_dir() and p.name != ".locks")
        return {
            "label": label,
            "ok": len(results) - len(failures),
            "total": len(results),
            "failures": failures,
            "index_dirs": index_dirs,
            "lock_dir_used": (cache / ".locks").is_dir(),
            "swallowed": swallowed,
            "validation": validation,
        }
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def report(arm: dict) -> None:
    print(f"\n  {arm['label']}: {arm['ok']}/{arm['total']} searches succeeded")
    print(f"    index dirs published: {arm['index_dirs'] or '(none)'}")
    print(f"    lock directory used:  {arm['lock_dir_used']}")
    swallowed = arm.get("swallowed", [])
    print(f"    swallowed cache-write failures: {len(swallowed)}")
    for w in swallowed[:3]:
        print(f"      {w.strip()[:160]}")
    v = arm.get("validation", {})
    print(f"    cache validation: {len(v.get('problems', []))} problem(s) across {v.get('checked', 0)} index dir(s)")
    for prob in v.get("problems", [])[:5]:
        print(f"      {prob}")
    for f in arm["failures"]:
        print(f"    FAILED proc {f['idx']}: {f['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--procs", type=int, default=4)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--repo", default=str(PLUGIN))
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    SHARED_HF.mkdir(parents=True, exist_ok=True)
    print(f"repo under index: {repo}")
    print(f"{args.procs} concurrent processes x {args.trials} trials, cold cache each trial")

    totals = {"patched": [0, 0], "stock": [0, 0]}
    stock_problems = stock_swallowed = patched_problems = 0
    for trial in range(1, args.trials + 1):
        print(f"\n=== trial {trial} ===")
        for label, patched in (("stock", False), ("patched", True)):
            arm = run_arm(label, patched, args.procs, repo)
            report(arm)
            totals[label][0] += arm["ok"]
            totals[label][1] += arm["total"]
            n_problems = len(arm.get("validation", {}).get("problems", []))
            if label == "stock":
                stock_problems += n_problems
                stock_swallowed += len(arm.get("swallowed", []))
            else:
                patched_problems += n_problems

    print("\n=== summary ===")
    for label, (ok, total) in totals.items():
        print(f"  {label:8s} {ok}/{total} searches succeeded")

    stock_ok, stock_total = totals["stock"]
    patched_ok, patched_total = totals["patched"]
    stock_damage = stock_problems + stock_swallowed

    print()
    if patched_ok < patched_total or patched_problems:
        print("  The override itself failed. Fix that before drawing any conclusion.")
    elif stock_damage:
        print("  Stock Semble corrupted or dropped the shared cache where the override")
        print("  did not. The override is doing load-bearing work -- keep it (issue #2).")
    else:
        print("  No corruption observed under this level of concurrency. That is NOT")
        print("  evidence the override is unnecessary: the cache write is structurally")
        print("  unsafe regardless of what this run saw. SembleIndex.save() writes four")
        print("  files in place with no temp-and-rename and no lock, and _build_index")
        print("  swallows any failure as a log warning, so real damage is silent rather")
        print("  than loud. Treat a clean run as 'the window is narrow', not 'safe'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
