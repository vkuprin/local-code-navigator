# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pyyaml==6.0.2",
# ]
# ///

"""Parse every manifest the plugin ships and assert the references between them resolve.

`claude plugin validate` checks the Claude manifests against their schema. It does not
know about the Codex manifests, the Serena context files, or whether a path written
inside an MCP config actually exists in the repository. This fills that gap.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "local-code-navigator"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f" -- {detail}"))
    if not ok:
        failures.append(label)


def parse_all_json() -> None:
    print("\n[json]")
    for path in sorted(ROOT.rglob("*.json")):
        if ".git" in path.parts or "node_modules" in path.parts:
            continue
        try:
            json.loads(path.read_text())
            check(f"parses {path.relative_to(ROOT)}", True)
        except json.JSONDecodeError as exc:
            check(f"parses {path.relative_to(ROOT)}", False, str(exc))


def parse_contexts() -> None:
    print("\n[serena contexts]")
    for path in sorted((PLUGIN / "contexts").glob("*.yml")):
        rel = path.relative_to(ROOT)
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            check(f"parses {rel}", False, str(exc))
            continue
        check(f"parses {rel}", True)
        check(f"{rel} has a prompt", bool(data.get("prompt")))
        check(f"{rel} excludes client-owned tools", bool(data.get("excluded_tools")))


def parse_skill() -> None:
    print("\n[skill]")
    path = PLUGIN / "skills" / "navigate-code" / "SKILL.md"
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    check("SKILL.md has front-matter", match is not None)
    if not match:
        return
    meta = yaml.safe_load(match.group(1))
    check("SKILL.md declares a name", bool(meta.get("name")))
    check("SKILL.md declares a description", bool(meta.get("description")))


def check_mcp_references() -> None:
    """Every path an MCP config points at must exist, with plugin variables stripped."""
    print("\n[mcp path references]")
    for name in (".mcp.json", ".mcp.claude.json"):
        config = json.loads((PLUGIN / name).read_text())
        for server, spec in config["mcpServers"].items():
            for arg in spec.get("args", []):
                if not isinstance(arg, str):
                    continue
                # Resolve both the Claude form (${CLAUDE_PLUGIN_ROOT}/x) and the Codex
                # form (./x, resolved against the plugin root via "cwd").
                candidate = arg.replace("${CLAUDE_PLUGIN_ROOT}/", "").lstrip("./")
                if not candidate.startswith(("contexts/", "scripts/")):
                    continue
                check(f"{name}:{server} -> {candidate}", (PLUGIN / candidate).exists(),
                      f"missing {PLUGIN / candidate}")


# Every token here is charged against the user's context on every session that loads
# the plugin, whether or not they ask a navigation question. The ceilings exist so
# growth is a deliberate decision with a number attached, not a slow drift. Raise them
# in the same change that adds the prose, and say why.
CONTEXT_BUDGET_CHARS = {
    "skills/navigate-code/SKILL.md": 3000,
    "contexts/claude-balanced.yml": 1800,
    "contexts/codex-balanced.yml": 1800,
}


def check_context_budget() -> None:
    """Report and bound the instruction footprint this plugin adds."""
    print("\n[context budget]")
    total = 0
    for rel, ceiling in CONTEXT_BUDGET_CHARS.items():
        path = PLUGIN / rel
        if not path.exists():
            check(f"{rel} exists", False, f"missing {path}")
            continue
        size = len(path.read_text())
        total += size
        pct = size / ceiling
        print(f"        {rel}: {size} chars ({pct:.0%} of {ceiling} budget, "
              f"~{size // 4} tokens)")
        check(f"{rel} within budget", size <= ceiling,
              f"{size} chars exceeds {ceiling}; raise the ceiling deliberately or trim")
    print(f"        total instruction footprint: {total} chars (~{total // 4} tokens)")


def check_hooks() -> None:
    """A hook manifest naming a script that is not there would fail silently."""
    print("\n[hooks]")
    manifest = PLUGIN / "hooks" / "hooks.json"
    if not manifest.exists():
        check("hooks manifest present", False, f"missing {manifest}")
        return
    data = json.loads(manifest.read_text())
    check("hooks manifest parses", True)
    commands = [h["command"]
                for entries in data.get("hooks", {}).values()
                for entry in entries
                for h in entry.get("hooks", [])
                if h.get("command")]
    check("hooks declare at least one command", bool(commands))
    for cmd in commands:
        rel = cmd.replace("${CLAUDE_PLUGIN_ROOT}/", "")
        target = PLUGIN / rel
        check(f"hook script exists: {rel}", target.exists(), f"missing {target}")
        if target.exists():
            check(f"hook script is executable: {rel}", target.stat().st_mode & 0o111 != 0)

    for name, key in ((".claude-plugin/plugin.json", "hooks"),
                      (".codex-plugin/plugin.json", "hooks")):
        d = json.loads((PLUGIN / name).read_text())
        check(f"{name} declares hooks", key in d, "hook manifest would not be loaded")


def check_pins_agree() -> None:
    """The launcher and its contract test must pin the same Semble version."""
    print("\n[version pins]")
    pattern = re.compile(r'"semble\[mcp\]==([0-9.]+)"')
    launcher = pattern.search((PLUGIN / "scripts" / "start_semble.py").read_text())
    contract = pattern.search((ROOT / "tests" / "semble_api_contract.py").read_text())
    check("launcher declares a semble pin", launcher is not None)
    check("api contract declares a semble pin", contract is not None)
    if launcher and contract:
        check("pins agree", launcher.group(1) == contract.group(1),
              f"launcher={launcher.group(1)} contract={contract.group(1)}")


def check_marketplaces() -> None:
    print("\n[marketplaces]")
    claude = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in claude["plugins"]:
        source = (ROOT / entry["source"]).resolve()
        check(f"claude marketplace -> {entry['name']}", source.is_dir(), f"missing {source}")

    codex = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    for entry in codex["plugins"]:
        source = (ROOT / entry["source"]["path"]).resolve()
        check(f"codex marketplace -> {entry['name']}", source.is_dir(), f"missing {source}")

    names = {e["name"] for e in claude["plugins"]} | {e["name"] for e in codex["plugins"]}
    check("both marketplaces list the same plugin names", len(names) == 1, f"names={names}")


def main() -> int:
    parse_all_json()
    parse_contexts()
    parse_skill()
    check_mcp_references()
    check_context_budget()
    check_hooks()
    check_pins_agree()
    check_marketplaces()

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nall configuration parsed and cross-references resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
