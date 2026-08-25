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
import hashlib
import json
import os
import subprocess
import sys
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "local-code-navigator"
EVALS = ROOT / "evals"
FIXTURE = EVALS / "fixture"
# Reassigned by main() when --repo targets a real repository.
CORPUS = FIXTURE

BUILTIN_TOOLS = ["Read", "Grep", "Glob"]
MCP_TOOLS_WRITE = [
    "mcp__serena__rename_symbol",
    "mcp__serena__replace_symbol_body",
]
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

# Process machinery rather than navigation. Counted separately from `calls` so the
# existing numbers stay comparable: a plugin that answers a named-file question by
# spawning a subagent and writing a todo list has not navigated better, it has spent
# more. `calls` keeps its old meaning; `orch_calls` is the over-routing signal.
ORCHESTRATION_TOOLS = {"Task", "Skill", "TodoWrite", "SlashCommand"}
# Both real-install arms get these so the comparison isolates the plugin, not the
# toolset. The control arm simply has no plugin skills to invoke.
ORCH_ALLOWED = ["Skill", "Task", "TodoWrite"]

# Colin Eberhardt's challenge to ponytail (issue #126): does a seven-word prompt do
# the same job as a whole plugin? Reproduced verbatim so the arm tests his claim and
# not a paraphrase of it.
YAGNI_PROMPT = "Follow YAGNI principles, and prefer one-liner solutions."

# Semantic-search tools only. The two docstring arms carry semble and nothing else,
# so any routing difference between them is the tool description and not the toolset.
SEMBLE_TOOLS = ["mcp__semble__search", "mcp__semble__find_related"]
DOCSTRING_ARMS = ("stock-doc", "proposed-doc")

# Arms that run a real install rather than --bare.
REAL_INSTALL_ARMS = ("under-test", "ecc", "control", "yagni")

# Set by main() for the real-install arms.
PLUGIN_UNDER_TEST: Path | None = None
ISOLATED_HOME: Path | None = None


def _git(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(workdir), capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "e@localhost",
             "GIT_COMMITTER_NAME": "eval", "GIT_COMMITTER_EMAIL": "e@localhost"})


def git_baseline(workdir: Path) -> bool:
    """Snapshot the scratch copy so `git diff` measures exactly what the agent wrote.

    -f on `add` because the corpus ships a .gitignore, and a file the agent creates
    that happens to match it would otherwise be silently uncounted -- which would
    understate whichever arm wrote it.
    """
    shutil.rmtree(workdir / ".git", ignore_errors=True)
    if _git(workdir, "init", "-q").returncode:
        return False
    _git(workdir, "add", "-A", "-f")
    return _git(workdir, "commit", "-q", "--no-gpg-sign", "-m", "baseline").returncode == 0


def git_added_lines(workdir: Path) -> tuple[int, int]:
    """Added lines and files touched, the same metric ponytail's own benchmark uses."""
    _git(workdir, "add", "-A", "-f")
    out = _git(workdir, "diff", "--cached", "--numstat", "HEAD")
    if out.returncode:
        return -1, -1
    added = files = 0
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].isdigit():
            added += int(parts[0])
            files += 1
    return added, files


def fixture_fingerprint() -> str:
    """Hash the corpus so a run that mutates it cannot pass silently.

    This is not hypothetical: Serena's project is pinned at server start, so a rename
    case whose MCP config still pointed at the real fixture rewrote the checked-in
    corpus while a benchmark was in flight. Ground truth silently changing underneath
    a measurement is the worst failure this suite can have.
    """
    digest = hashlib.sha256()
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(CORPUS)
        # Serena writes .serena/ wherever it activates a project and Python drops
        # __pycache__ next to anything it imports. Those appear on a perfectly clean
        # run, so hashing them turns the guard into a false alarm that cries wolf on
        # every measurement.
        if any(part in (".serena", "__pycache__", ".git") for part in rel.parts):
            continue
        if rel.suffix in (".pyc", ".pyo"):
            continue
        digest.update(str(rel).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def route_of(tool: str) -> str:
    if tool.startswith("mcp__serena__"):
        return "serena"
    if tool.startswith("mcp__semble__"):
        return "semble"
    return "builtin"


def resolved_mcp_config(tmp: Path, context: str | None = None,
                        project: Path | None = None, tag: str = "") -> Path:
    """Materialize .mcp.claude.json with plugin variables expanded.

    `context` swaps Serena's context file. Passing "claude-code" selects Serena's own
    stock context instead of this plugin's, which is what isolates the plugin's actual
    contribution: the two exclude the identical six tools, so the only difference is
    prompt wording.
    """
    data_dir = tmp / "plugin-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    raw = (PLUGIN / ".mcp.claude.json").read_text()
    raw = raw.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
    raw = raw.replace("${CLAUDE_PLUGIN_DATA}", str(data_dir))
    raw = raw.replace("${CLAUDE_PROJECT_DIR}", str(project or CORPUS))
    if context:
        raw = raw.replace(f"{PLUGIN}/contexts/claude-balanced.yml", context)
    out = tmp / f"mcp-{tag or context or 'plugin'}.json"
    out.write_text(raw)
    return out


def skill_body() -> str:
    text = (PLUGIN / "skills" / "navigate-code" / "SKILL.md").read_text()
    # Drop the front-matter; keep the guidance.
    if text.startswith("---"):
        text = text.split("---", 2)[-1]
    return text.strip()


def run_case(case: dict, arm: str, model: str, configs: dict[str, Path],
             timeout: int) -> dict:
    allowed = list(BUILTIN_TOOLS)
    workdir = CORPUS
    scratch: Path | None = None
    if case.get("mutates"):
        # Copy the fixture so an edit cannot leak into the next run or the repository.
        scratch = Path(tempfile.mkdtemp(prefix="lcn-mutate-"))
        workdir = scratch / "fixture"
        shutil.copytree(CORPUS, workdir)
        git_baseline(workdir)
        allowed += ["Edit", "Write"]
        configs = dict(configs)
        configs["plugin"] = resolved_mcp_config(scratch, project=workdir, tag="plugin")
        configs["stock"] = resolved_mcp_config(scratch, "claude-code", workdir, "stock")
    # A real plugin install cannot be measured under --bare. Verified empirically:
    # with `--bare --plugin-dir <ecc>` the plugin loads (skills go 15 -> 337 in the
    # init event) but asked to name its own skills the model answers NONE -- the
    # descriptions never reach it, so it pays no context and gets no guidance. These
    # arms therefore drop --bare and isolate with CLAUDE_CONFIG_DIR instead.
    real_install = arm in REAL_INSTALL_ARMS
    cmd = ["claude", "-p", case["prompt"]]
    if not real_install:
        cmd.append("--bare")
    cmd += [
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        # Generous headroom on purpose. The baseline arm often needs more calls than
        # the plugin arm, and truncating it produces missing data that looks like a
        # loss. Budget adherence is scored separately from being allowed to finish.
        "--max-turns", str(case.get("max_tool_calls", 8) * 2 + 6),
        "--strict-mcp-config",
    ]
    if case.get("mutates") and arm != "baseline":
        allowed += MCP_TOOLS_WRITE
    if arm == "plugin":
        allowed += MCP_TOOLS + ["ToolSearch"]
        cmd += ["--mcp-config", str(configs["plugin"]),
                "--append-system-prompt", skill_body()]
    elif arm == "stock":
        # Same servers, Serena's own context, no navigate-code guidance. The delta
        # between this and `plugin` is the plugin's actual contribution.
        allowed += MCP_TOOLS + ["ToolSearch"]
        cmd += ["--mcp-config", str(configs["stock"])]
    elif arm in DOCSTRING_ARMS:
        # Identical corpus, identical prebuilt index, identical binary except for one
        # docstring. Whatever separates these two arms is the wording, nothing else.
        allowed += SEMBLE_TOOLS + ["ToolSearch"]
        cmd += ["--mcp-config", str(configs[arm])]
    elif real_install:
        allowed += ORCH_ALLOWED
        cmd += ["--mcp-config", str(configs["empty"])]
        if arm in ("under-test", "ecc"):
            cmd += ["--plugin-dir", str(PLUGIN_UNDER_TEST)]
        elif arm == "yagni":
            cmd += ["--append-system-prompt", YAGNI_PROMPT]
    else:
        cmd += ["--mcp-config", str(configs["empty"])]
    cmd += ["--allowed-tools", *allowed]

    try:
        env = {**os.environ}
        if real_install:
            # Without this the developer's own ~/.claude leaks in: a --bare run still
            # reported 10 personal plugins in its init event. A throwaway config dir
            # reports `plugins: NONE`, which is what a control arm has to mean.
            env["CLAUDE_CONFIG_DIR"] = str(ISOLATED_HOME)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(workdir), env=env,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
        return {"error": "timeout", "tools": [], "answer": "", "cost": 0.0}

    tools: list[str] = []
    answer = ""
    cost = 0.0
    duration_ms = 0
    api_ms = 0
    tokens_in = tokens_out = 0
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
            duration_ms = int(event.get("duration_ms") or 0)
            api_ms = int(event.get("duration_api_ms") or 0)
            # usage.input_tokens counts only the uncached remainder, which on a
            # repeated prompt is a handful of tokens and says nothing about how much
            # context the run actually consumed. modelUsage carries the real totals.
            usage = event.get("usage") or {}
            tokens_out = int(usage.get("output_tokens") or 0)
            tokens_in = 0
            for stats in (event.get("modelUsage") or {}).values():
                tokens_in += int(stats.get("inputTokens") or 0)
                tokens_in += int(stats.get("cacheReadInputTokens") or 0)
                tokens_in += int(stats.get("cacheCreationInputTokens") or 0)
            if not tokens_in:
                tokens_in = int(usage.get("input_tokens") or 0) + int(
                    usage.get("cache_read_input_tokens") or 0)

    file_checks: dict[str, bool] = {}
    for spec in case.get("expect_file_contains", []):
        target = workdir / spec["path"]
        text = target.read_text() if target.exists() else ""
        file_checks[f"{spec['path']} contains {spec['text']!r}"] = spec["text"] in text
    for spec in case.get("expect_file_lacks", []):
        target = workdir / spec["path"]
        text = target.read_text() if target.exists() else ""
        file_checks[f"{spec['path']} lacks {spec['text']!r}"] = spec["text"] not in text
    loc_added, files_touched = (-1, -1)
    if scratch:
        loc_added, files_touched = git_added_lines(workdir)
        shutil.rmtree(scratch, ignore_errors=True)

    if not answer:
        reason = ("exhausted max-turns after "
                  f"{len(tools)} tool calls" if tools else
                  (proc.stderr or "no output")[-300:])
        return {"error": reason, "tools": tools, "answer": "", "cost": cost,
                "file_checks": file_checks, "duration_ms": duration_ms,
                "api_ms": api_ms, "tokens_in": tokens_in, "tokens_out": tokens_out,
                "loc_added": loc_added, "files_touched": files_touched}
    return {"error": None, "tools": tools, "answer": answer, "cost": cost,
            "file_checks": file_checks, "duration_ms": duration_ms,
            "api_ms": api_ms, "tokens_in": tokens_in, "tokens_out": tokens_out,
            "loc_added": loc_added, "files_touched": files_touched}


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
                              env={**os.environ}, stdin=subprocess.DEVNULL)
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
        "loc_added": outcome.get("loc_added", -1),
        "files_touched": outcome.get("files_touched", -1),
        "orch_calls": sum(1 for t in tools if t in ORCHESTRATION_TOOLS),
        "orch_tools": [t for t in tools if t in ORCHESTRATION_TOOLS],
        "within_budget": len(substantive) <= case.get("max_tool_calls", 8),
        "error": outcome["error"],
        "cost": outcome["cost"],
        "duration_ms": outcome.get("duration_ms", 0),
        "api_ms": outcome.get("api_ms", 0),
        "tokens_in": outcome.get("tokens_in", 0),
        "tokens_out": outcome.get("tokens_out", 0),
        "answer": (outcome["answer"] or "")[:1500],
        "tools": tools,
        "file_checks": outcome.get("file_checks") or {},
        "files_ok": (all((outcome.get("file_checks") or {}).values())
                     if outcome.get("file_checks") else None),
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
    parser.add_argument("--arms", default="plugin,baseline",
                        help="plugin (custom context + skill), stock (Serena's own "
                             "context, no skill), baseline (no MCP at all), "
                             "ecc (real plugin install, no --bare), control "
                             "(same real-install mode with no plugin)")
    parser.add_argument("--stock-doc-config", default="/tmp/mcp-semble-stock.json",
                        help="MCP config for the `stock-doc` arm")
    parser.add_argument("--proposed-doc-config", default="/tmp/mcp-semble-proposed.json",
                        help="MCP config for the `proposed-doc` arm")
    parser.add_argument("--plugin-under-test", "--ecc-plugin-dir", dest="plugin_under_test",
                        help="directory of the plugin to load for the `under-test` arm")
    parser.add_argument("--isolated-home",
                        help="throwaway CLAUDE_CONFIG_DIR for the real-install arms "
                             "(default: a fresh temp dir per run)")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--max-cost-usd", type=float, default=5.0)
    parser.add_argument("--judge-model", default="haiku")
    parser.add_argument("--cases", default=str(EVALS / "cases.yaml"),
                        help="case definitions to run")
    parser.add_argument("--allow-mutating", action="store_true",
                        help="permit mutating cases against --repo; each run still "
                             "works on its own copy, so point --repo at a snapshot")
    parser.add_argument("--repo",
                        help="run against a real repository instead of the "
                             "synthetic fixture; mutating cases are refused")
    parser.add_argument("--no-judge", action="store_true",
                        help="skip semantic grading (routing and literal checks only)")
    parser.add_argument("--json", help="write full results here")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is required: `claude --bare` never reads OAuth or the keychain.")
        return 2

    global CORPUS
    if args.repo:
        CORPUS = Path(args.repo).resolve()
        if not CORPUS.is_dir():
            print(f"--repo is not a directory: {CORPUS}")
            return 2

    cases = yaml.safe_load(Path(args.cases).read_text())
    if args.repo and not args.allow_mutating:
        mutating = [c["id"] for c in cases if c.get("mutates")]
        if mutating:
            print(f"refusing to run mutating cases against {CORPUS}: {mutating}")
            print("Rename cases edit files. Point --repo at a disposable snapshot and")
            print("pass --allow-mutating if that is what you meant.")
            return 2
    if args.case:
        cases = [c for c in cases if args.case in c["id"]]
    if not cases:
        print("no cases matched")
        return 2

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    tmp = Path(tempfile.mkdtemp(prefix="lcn-eval-"))

    global PLUGIN_UNDER_TEST, ISOLATED_HOME
    if set(REAL_INSTALL_ARMS) & set(arms):
        ISOLATED_HOME = Path(args.isolated_home) if args.isolated_home else (
            tmp / "isolated-home")
        ISOLATED_HOME.mkdir(parents=True, exist_ok=True)
        if {"under-test", "ecc"} & set(arms):
            if not args.plugin_under_test:
                print("--plugin-under-test is required for the `under-test` arm")
                return 2
            PLUGIN_UNDER_TEST = Path(args.plugin_under_test).resolve()
            if not (PLUGIN_UNDER_TEST / ".claude-plugin" / "plugin.json").is_file():
                print(f"no .claude-plugin/plugin.json under {PLUGIN_UNDER_TEST}")
                return 2
    empty_config = tmp / "mcp-empty.json"
    empty_config.write_text(json.dumps({"mcpServers": {}}))
    configs = {
        "plugin": resolved_mcp_config(tmp),
        "stock": resolved_mcp_config(tmp, "claude-code"),
        "empty": empty_config,
        "stock-doc": Path(args.stock_doc_config),
        "proposed-doc": Path(args.proposed_doc_config),
    }
    for a in DOCSTRING_ARMS:
        if a in arms and not configs[a].is_file():
            print(f"missing MCP config for arm {a}: {configs[a]}")
            return 2

    # Hashing a large repository is slow, and nothing may mutate it anyway.
    fingerprint_before = None if args.repo else fixture_fingerprint()
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
                outcome = run_case(case, arm, args.model, configs, args.timeout)
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
                    badf = [k for k, v in (s["file_checks"] or {}).items() if not v]
                    if badf:
                        flags.append(f"FILE CHECK FAILED: {badf[0][:70]}")
                    if not s["within_budget"]:
                        flags.append(f"{s['calls']} calls over budget")
                    if s["orch_calls"]:
                        flags.append(f"orch {s['orch_tools']}")
                print(f"  {arm:9s} run{run}: {s['calls']} calls  ${s['cost']:.4f}  " + "; ".join(flags))

    if fingerprint_before is not None and fixture_fingerprint() != fingerprint_before:
        print("\n*** FIXTURE MUTATED DURING THE RUN ***")
        print("The corpus changed while it was being measured, so these results are")
        print("not trustworthy. Restore it with `git checkout -- evals/fixture/` and")
        print("check that mutating cases point Serena's --project at their scratch copy.")
        return 3

    print(f"\n=== aggregate (spent ${spent:.3f}) ===")
    agg: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in results:
        agg[(r["arm"], "all")].append(r)

    header = (f"  {'arm':9s} {'route':>7s} {'tool':>6s} {'evidence':>9s} "
              f"{'claims':>7s} {'judged':>7s} {'files':>7s} {'budget':>7s} "
              f"{'calls':>6s} {'orch':>5s} {'loc':>6s} {'tok_in':>9s} "
              f"{'wall_s':>7s} {'cost$':>8s}")
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
            "wall_s": sum(r["duration_ms"] for r in rows) / n / 1000,
            "api_s": sum(r["api_ms"] for r in rows) / n / 1000,
            "tokens_out": sum(r["tokens_out"] for r in rows) / n,
            "tokens_in": sum(r["tokens_in"] for r in rows) / n,
            "orch_calls": sum(r["orch_calls"] for r in rows) / n,
            "loc_added": (sum(r["loc_added"] for r in rows if r["loc_added"] >= 0)
                          / max(1, sum(1 for r in rows if r["loc_added"] >= 0))),
            "cost": sum(r["cost"] for r in rows) / n,
        }
        file_rows = [r for r in rows if r.get("files_ok") is not None]
        stats["files"] = (sum(r["files_ok"] for r in file_rows) / len(file_rows)
                          if file_rows else float("nan"))
        judged_rows = [r for r in rows if r.get("judged_clean") is not None]
        stats["judged"] = (sum(r["judged_clean"] for r in judged_rows) / len(judged_rows)
                           if judged_rows else float("nan"))
        summary[arm] = stats
        judged = "n/a" if stats["judged"] != stats["judged"] else f"{stats['judged']:.0%}"
        files = "n/a" if stats["files"] != stats["files"] else f"{stats['files']:.0%}"
        print(f"  {arm:9s} {stats['route']:>7.0%} {stats['tool_used']:>6.0%} "
              f"{stats['evidence']:>9.0%} {stats['claims']:>7.0%} {judged:>7s} "
              f"{files:>7s} {stats['budget']:>7.0%} {stats['calls']:>6.1f} "
              f"{stats['orch_calls']:>5.1f} {stats['loc_added']:>6.0f} "
              f"{stats['tokens_in']:>9,.0f} "
              f"{stats['wall_s']:>7.1f} {stats['cost']:>8.4f}")

    if "proposed-doc" in summary and "stock-doc" in summary:
        print("\n  ablation delta (proposed-doc - stock-doc):")
        print("  Same corpus, same prebuilt index, same semble build. The two arms differ")
        print("  by one docstring, so every delta below is the wording and nothing else.")
        for key in ("route", "tool_used", "evidence", "claims", "judged"):
            if summary["proposed-doc"][key] != summary["proposed-doc"][key]:
                continue
            d = summary["proposed-doc"][key] - summary["stock-doc"][key]
            print(f"    {key:9s} {d:+.0%}")
        for key, fmt in (("calls","+.1f"), ("tokens_in","+,.0f"), ("cost","+.4f")):
            print(f"    {key:9s} {summary['proposed-doc'][key] - summary['stock-doc'][key]:{fmt}}")

    probe = "under-test" if "under-test" in summary else "ecc"
    if probe in summary and "control" in summary:
        print(f"\n  ablation delta ({probe} - control):")
        print("  Both arms run the same real-install mode against the same corpus with")
        print("  the same allowed tools. The only difference is --plugin-dir, so every")
        print("  delta below is the plugin's own contribution.")
        for key in ("route", "evidence", "claims", "judged", "budget"):
            if summary[probe][key] != summary[probe][key]:
                continue
            print(f"    {key:9s} {summary['ecc'][key] - summary['control'][key]:+.0%}")
        for key, fmt in (("calls", "+.1f"), ("orch_calls", "+.1f"),
                         ("tokens_in", "+,.0f"), ("wall_s", "+.1f"),
                         ("cost", "+.4f")):
            d = summary[probe][key] - summary["control"][key]
            print(f"    {key:9s} {d:{fmt}}")
        ratio = (summary[probe]["tokens_in"] / summary["control"]["tokens_in"]
                 if summary["control"]["tokens_in"] else float("nan"))
        print(f"    {'tok ratio':9s} {ratio:.2f}x")

    if "plugin" in summary and "baseline" in summary:
        print("\n  ablation delta (plugin - baseline):")
        print("  NOTE: on cases expecting serena or semble the baseline scores 0% on")
        print("  route by construction -- it has no such tools to choose. Read route")
        print("  as a plugin-arm diagnostic; compare arms on calls, evidence and judged.")
        for key in ("route", "tool_used", "evidence", "claims", "judged", "files", "budget"):
            if summary["plugin"][key] != summary["plugin"][key]:
                continue
            d = summary["plugin"][key] - summary["baseline"][key]
            print(f"    {key:9s} {d:+.0%}")
        dc = summary["plugin"]["calls"] - summary["baseline"]["calls"]
        print(f"    {'calls':9s} {dc:+.1f}")
        dw = summary["plugin"]["wall_s"] - summary["baseline"]["wall_s"]
        print(f"    {'wall_s':9s} {dw:+.1f}")
        dt = summary["plugin"]["cost"] - summary["baseline"]["cost"]
        print(f"    {'cost$':9s} {dt:+.4f}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"model": args.model, "runs": args.runs, "spent_usd": spent,
             "results": results, "summary": summary}, indent=2))
        print(f"\nwrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
