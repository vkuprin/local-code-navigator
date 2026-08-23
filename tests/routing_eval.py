# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pyyaml==6.0.2",
# ]
# ///

"""Score the navigate-code routing contract against a no-plugin baseline.

Issue #7 asks for regression cases that check which route is selected first, not just
whether the final answer is right. Issue #1 asks for a redistributable corpus. This
runs the cases in evals/cases.yaml over the fixture in evals/fixture/ and reports
routing, evidence, prohibited claims, and call count as four separate scores.

Each case runs twice:

  plugin    the plugin's own MCP config plus the navigate-code guidance
  baseline  built-in tools only, no MCP servers

Runs use `claude -p --bare`, which skips hooks, CLAUDE.md auto-discovery, plugin sync
and auto-memory, so a developer's personal configuration cannot leak into the result.
`--bare` authenticates strictly via ANTHROPIC_API_KEY.

Fidelity caveat worth knowing before trusting a number: the plugin arm injects the
skill body with --append-system-prompt, because --bare does not sync installed plugins.
A real install exposes the skill lazily instead, so this arm sees the guidance somewhat
more strongly than a real session would. It measures whether the guidance changes
routing, which is the question, but it is not a substitute for `claude plugin eval`
once that is out of early access.

Usage:
  export ANTHROPIC_API_KEY=...
  uv run --python 3.12 --script tests/routing_eval.py --runs 1 --model haiku
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "local-code-navigator"
EVALS = ROOT / "evals"
FIXTURE = EVALS / "fixture"

BUILTIN_TOOLS = ["Read", "Grep", "Glob"]
MCP_TOOLS = [
    "mcp__serena__find_symbol",
    "mcp__serena__find_referencing_symbols",
    "mcp__serena__find_implementations",
    "mcp__serena__get_symbols_overview",
    "mcp__serena__find_declaration",
    "mcp__semble__search",
    "mcp__semble__find_related",
]
# Loading a deferred tool's schema is bookkeeping, not a routing decision.
ROUTE_NEUTRAL = {"ToolSearch", "Skill", "TodoWrite"}


def route_of(tool: str) -> str:
    if tool.startswith("mcp__serena__"):
        return "serena"
    if tool.startswith("mcp__semble__"):
        return "semble"
    return "builtin"


def resolved_mcp_config(tmp: Path) -> Path:
    """Materialize .mcp.claude.json with plugin variables expanded."""
    data_dir = tmp / "plugin-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    raw = (PLUGIN / ".mcp.claude.json").read_text()
    raw = raw.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
    raw = raw.replace("${CLAUDE_PLUGIN_DATA}", str(data_dir))
    raw = raw.replace("${CLAUDE_PROJECT_DIR}", str(FIXTURE))
    out = tmp / "mcp-plugin.json"
    out.write_text(raw)
    return out


def skill_body() -> str:
    text = (PLUGIN / "skills" / "navigate-code" / "SKILL.md").read_text()
    # Drop the front-matter; keep the guidance.
    if text.startswith("---"):
        text = text.split("---", 2)[-1]
    return text.strip()


def run_case(case: dict, arm: str, model: str, mcp_config: Path,
             empty_config: Path, timeout: int) -> dict:
    allowed = list(BUILTIN_TOOLS)
    cmd = [
        "claude", "-p", case["prompt"], "--bare",
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        # Generous headroom on purpose. The baseline arm often needs more calls than
        # the plugin arm, and truncating it produces missing data that looks like a
        # loss. Budget adherence is scored separately from being allowed to finish.
        "--max-turns", str(case.get("max_tool_calls", 8) * 2 + 6),
        "--strict-mcp-config",
    ]
    if arm == "plugin":
        allowed += MCP_TOOLS + ["ToolSearch"]
        cmd += ["--mcp-config", str(mcp_config),
                "--append-system-prompt", skill_body()]
    else:
        cmd += ["--mcp-config", str(empty_config)]
    cmd += ["--allowed-tools", *allowed]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(FIXTURE), env={**os.environ})
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "tools": [], "answer": "", "cost": 0.0}

    tools: list[str] = []
    answer = ""
    cost = 0.0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    tools.append(block["name"])
        elif event.get("type") == "result":
            answer = str(event.get("result") or "")
            cost = float(event.get("total_cost_usd") or 0.0)

    if not answer and proc.returncode != 0:
        return {"error": (proc.stderr or "no output")[-300:], "tools": tools,
                "answer": "", "cost": cost}
    return {"error": None, "tools": tools, "answer": answer, "cost": cost}


JUDGE_PROMPT = """You are grading one assertion about an AI assistant's answer.

ASSERTION: {assertion}

ANSWER UNDER TEST:
<answer>
{answer}
</answer>

Reply with exactly one word: YES if the assertion is true of the answer, NO if it is
not. No explanation."""


def judge(assertion: str, answer: str, model: str, timeout: int) -> bool | None:
    """Grade one semantic assertion. Returns None if grading itself failed.

    Some assertions cannot be expressed as a substring. "Did it present a same-name
    match as a real reference" is the important one here: an answer that names the
    decoy in order to exclude it is correct, and a substring check marks it wrong.
    """
    cmd = ["claude", "-p", JUDGE_PROMPT.format(assertion=assertion, answer=answer[:4000]),
           "--bare", "--model", model, "--max-turns", "1"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ})
    except subprocess.TimeoutExpired:
        return None
    verdict = (proc.stdout or "").strip().upper()
    if verdict.startswith("YES"):
        return True
    if verdict.startswith("NO"):
        return False
    return None


def _normalize(text: str) -> str:
    """Lowercase, and strip digit grouping so 18,200 matches 18200."""
    out = []
    for i, ch in enumerate(text):
        if ch in ",_" and 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
            continue
        out.append(ch)
    return "".join(out).lower()


def score(case: dict, outcome: dict, judgements: dict | None = None) -> dict:
    tools = outcome["tools"]
    answer_lc = _normalize(outcome["answer"] or "")
    substantive = [t for t in tools if t not in ROUTE_NEUTRAL]
    first_route = route_of(substantive[0]) if substantive else None

    expected_tools = case.get("expect_tools") or []
    return {
        "route": first_route == case["expect_first_route"],
        "first_route": first_route,
        "expected_route": case["expect_first_route"],
        "used_expected_tools": all(t in tools for t in expected_tools),
        "evidence": all(_normalize(s) in answer_lc for s in case.get("must_include", [])),
        "missing_evidence": [s for s in case.get("must_include", [])
                             if _normalize(s) not in answer_lc],
        "claims_clean": not any(_normalize(s) in answer_lc
                                for s in case.get("must_exclude", [])),
        "prohibited_found": [s for s in case.get("must_exclude", [])
                             if _normalize(s) in answer_lc],
        "calls": len(substantive),
        "within_budget": len(substantive) <= case.get("max_tool_calls", 8),
        "error": outcome["error"],
        "cost": outcome["cost"],
        "answer": (outcome["answer"] or "")[:1500],
        "tools": tools,
        "judgements": judgements or {},
        "judged_clean": (
            all(v for v in judgements.values() if v is not None)
            if judgements and any(v is not None for v in judgements.values())
            else None),
        "judge_errors": sum(1 for v in (judgements or {}).values() if v is None),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="runs per case per arm")
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--case", help="only run cases whose id contains this")
    parser.add_argument("--arms", default="plugin,baseline")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--max-cost-usd", type=float, default=5.0)
    parser.add_argument("--judge-model", default="haiku")
    parser.add_argument("--no-judge", action="store_true",
                        help="skip semantic grading (routing and literal checks only)")
    parser.add_argument("--json", help="write full results here")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is required: `claude --bare` never reads OAuth or the keychain.")
        return 2

    cases = yaml.safe_load((EVALS / "cases.yaml").read_text())
    if args.case:
        cases = [c for c in cases if args.case in c["id"]]
    if not cases:
        print("no cases matched")
        return 2

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    tmp = Path(tempfile.mkdtemp(prefix="lcn-eval-"))
    mcp_config = resolved_mcp_config(tmp)
    empty_config = tmp / "mcp-empty.json"
    empty_config.write_text(json.dumps({"mcpServers": {}}))

    results = []
    spent = 0.0
    print(f"{len(cases)} cases x {len(arms)} arms x {args.runs} run(s), model={args.model}")

    for case in cases:
        print(f"\n=== {case['id']}  (expects {case['expect_first_route']}) ===")
        for arm in arms:
            for run in range(args.runs):
                if spent >= args.max_cost_usd:
                    print(f"  cost ceiling ${args.max_cost_usd} reached; stopping")
                    break
                outcome = run_case(case, arm, args.model, mcp_config, empty_config, args.timeout)
                judgements = {}
                if outcome["answer"] and not args.no_judge:
                    for a in case.get("judge_assertions", []):
                        verdict = judge(a["assertion"], outcome["answer"],
                                        args.judge_model, args.timeout)
                        # Store whether the case's expectation was met.
                        judgements[a["assertion"]] = (
                            None if verdict is None else verdict == a["expect"])
                s = score(case, outcome, judgements)
                spent += s["cost"]
                results.append({"case": case["id"], "arm": arm, "run": run, **s})
                flags = []
                if s["error"]:
                    flags.append(f"ERROR {s['error'][:60]}")
                else:
                    flags.append("route OK" if s["route"] else f"route {s['first_route']} != {s['expected_route']}")
                    if not s["evidence"]:
                        flags.append(f"missing {s['missing_evidence']}")
                    if not s["claims_clean"]:
                        flags.append(f"PROHIBITED {s['prohibited_found']}")
                    bad = [a for a, v in (s["judgements"] or {}).items() if v is False]
                    if bad:
                        flags.append(f"JUDGE FAILED: {bad[0][:70]}")
                    if not s["within_budget"]:
                        flags.append(f"{s['calls']} calls over budget")
                print(f"  {arm:9s} run{run}: {s['calls']} calls  ${s['cost']:.4f}  " + "; ".join(flags))

    print(f"\n=== aggregate (spent ${spent:.3f}) ===")
    agg: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in results:
        agg[(r["arm"], "all")].append(r)

    header = (f"  {'arm':9s} {'route':>7s} {'tool':>6s} {'evidence':>9s} "
              f"{'claims':>7s} {'judged':>7s} {'budget':>7s} {'calls':>6s}")
    print(header)
    summary = {}
    for arm in arms:
        rows = [r for r in results if r["arm"] == arm and not r["error"]]
        if not rows:
            print(f"  {arm:9s}   (no successful runs)")
            continue
        n = len(rows)
        stats = {
            "route": sum(r["route"] for r in rows) / n,
            "evidence": sum(r["evidence"] for r in rows) / n,
            "claims": sum(r["claims_clean"] for r in rows) / n,
            "budget": sum(r["within_budget"] for r in rows) / n,
            "calls": sum(r["calls"] for r in rows) / n,
            "tool_used": sum(r["used_expected_tools"] for r in rows) / n,
        }
        judged_rows = [r for r in rows if r.get("judged_clean") is not None]
        stats["judged"] = (sum(r["judged_clean"] for r in judged_rows) / len(judged_rows)
                           if judged_rows else float("nan"))
        summary[arm] = stats
        judged = "n/a" if stats["judged"] != stats["judged"] else f"{stats['judged']:.0%}"
        print(f"  {arm:9s} {stats['route']:>7.0%} {stats['tool_used']:>6.0%} "
              f"{stats['evidence']:>9.0%} {stats['claims']:>7.0%} {judged:>7s} "
              f"{stats['budget']:>7.0%} {stats['calls']:>6.1f}")

    if "plugin" in summary and "baseline" in summary:
        print("\n  ablation delta (plugin - baseline):")
        print("  NOTE: on cases expecting serena or semble the baseline scores 0% on")
        print("  route by construction -- it has no such tools to choose. Read route")
        print("  as a plugin-arm diagnostic; compare arms on calls, evidence and judged.")
        for key in ("route", "tool_used", "evidence", "claims", "judged", "budget"):
            if summary["plugin"][key] != summary["plugin"][key]:
                continue
            d = summary["plugin"][key] - summary["baseline"][key]
            print(f"    {key:9s} {d:+.0%}")
        dc = summary["plugin"]["calls"] - summary["baseline"]["calls"]
        print(f"    {'calls':9s} {dc:+.1f}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"model": args.model, "runs": args.runs, "spent_usd": spent,
             "results": results, "summary": summary}, indent=2))
        print(f"\nwrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
