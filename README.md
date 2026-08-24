# Local Code Navigator

Symbol-aware and semantic code navigation for Claude Code and Codex, with a routing
rule that decides which one — or neither — should answer a given question.

- [Serena](https://github.com/oraios/serena) resolves symbols, references, implementations, diagnostics, and symbolic edits.
- [Semble](https://github.com/MinishLab/semble) finds code by behavior when you do not know the name.
- Your agent's built-in tools stay the right answer for literal text and for reading a file you can already name.

## What this measured, including the part that failed

Bundling two MCP servers is convenience, not a reason to exist — you can add both by
hand in two commands. The claim worth testing was that Serena's own guidance is too
aggressive and a milder routing rule does better. On a nine-file synthetic fixture with
`haiku`, it did: 1.9 tool calls against 5.2, same correctness.

**That result did not survive a real repository.** Re-run over a frozen 330-file
snapshot with `sonnet`, 54 runs, three arms:

| arm | route | correctness | mean calls | context (tok_in) | cost |
|---|---:|---:|---:|---:|---:|
| this plugin | 67% | **89%** | 3.4 | **1,079,404** | $0.0257 |
| Serena's stock context | 50% | 100% | 3.0 | 812,169 | $0.0214 |
| no MCP servers | 33% | 100% | 3.2 | **212,886** | **$0.0162** |

Three things go wrong at once, and they are worth stating plainly:

**It costs 5.1x more context.** Serena's central pitch is that reading one symbol beats
reading a whole file. Measured, the opposite happens: the tool schemas for 21 Serena
tools and 2 Semble tools load into context on every turn, and that overhead dwarfs any
saving from symbol-level reads. This holds even on the case built specifically to
favour it — locating a 10-line function inside a 1276-line, 18k-token file cost 49,174
tokens with the plugin and 9,565 without it.

**It is less correct on its own flagship case.** Asked for real references to a symbol
with four same-name decoys, the plugin arm answered correctly once in three runs. Twice
it reported line 925 where the answer is 926 — Serena returns 0-based lines, the skill
says to add one, and the model applied that to the definition and forgot it for the
reference *in the same answer*. A literal text search cannot make this mistake, because
it reports 1-based lines. Both other arms scored 100%.

**The call-count advantage decays.** Fixture with `haiku`: 1.9 against 5.2. Same fixture
with `sonnet`: 3.8 against 5.3. Real repository with `sonnet`: 3.4 against 3.2. Both the
stronger model and the realistic corpus eat into it, and together they erase it.

### What still stands

One case survived: renaming a symbol on the fixture took 6.3 calls against the
baseline's 18.3, at less than half the cost. Symbolic edits are the part of Serena that
text tools genuinely struggle to match. On the real repository the same case narrowed to
4.0 calls against 5.3, with the baseline still cheaper.

### What this means if you are deciding whether to install it

On a strong model, against a real codebase, this plugin currently costs more context,
more money, and is not more correct. Install it if you specifically want semantic
discovery or symbolic refactoring and are willing to pay for the context; do not install
it expecting fewer steps or better answers. The measurements above are reproducible —
[`tests/routing_eval.py`](tests/routing_eval.py), raw per-run data in
[`evals/results/`](evals/results/), caveats in [BENCHMARKS.md](BENCHMARKS.md).

Installing contributes both MCP servers and the matching guidance; removing takes both
away, so the skill never advertises tools you do not have.

## Prerequisite

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) so `uv` and `uvx` are available on `PATH`. The first launch downloads the pinned Python packages, and Semble downloads its compact embedding model when its MCP server first starts.

## Install for Claude Code

```bash
claude plugin marketplace add vkuprin/local-code-navigator
claude plugin install local-code-navigator@vkuprin-tools --scope user
```

Run `/reload-plugins` in Claude Code, or restart it, after installation or updates.

If Serena or Semble is already registered directly, inspect the configured scope and remove the duplicate registration before starting a plugin-enabled session:

```bash
claude mcp list
claude mcp remove serena
claude mcp remove semble
```

Verify with `claude plugin details local-code-navigator@vkuprin-tools` and `/mcp`.

### Migrating from 1.0.x

Version 1.1.0 replaces the old `serena-semble` install ID. Remove the old Claude Code plugin before installing the new one:

```bash
claude plugin uninstall serena-semble@vkuprin-tools --scope user
claude plugin marketplace update vkuprin-tools
claude plugin install local-code-navigator@vkuprin-tools --scope user
```

Then run `/reload-plugins` or restart Claude Code.

## Install for Codex

```bash
codex plugin marketplace add vkuprin/local-code-navigator
codex plugin add local-code-navigator@vkuprin-tools
```

Start a new Codex thread after installation so the new skill and MCP tools are loaded. If Serena or Semble is already configured directly, inspect `codex mcp list` and remove the duplicate with `codex mcp remove <name>`.

## Update

Claude Code:

```bash
claude plugin marketplace update vkuprin-tools
claude plugin update local-code-navigator@vkuprin-tools --scope user
```

Then run `/reload-plugins` or restart Claude Code.

Codex:

```bash
codex plugin marketplace upgrade vkuprin-tools
codex plugin add local-code-navigator@vkuprin-tools
```

Then start a new thread.

## Uninstall

```bash
claude plugin uninstall local-code-navigator@vkuprin-tools --scope user
codex plugin remove local-code-navigator@vkuprin-tools
```

Claude Code deletes its plugin data directory on the final uninstall unless `--keep-data` is passed. Codex and Semble may retain ordinary package, model, and index caches in their standard user cache locations.

## Tool boundary

| Question | Best first route |
|---|---|
| Where is behavior like this implemented? | Semble semantic search |
| What is this symbol and who references it? | Serena symbol intelligence |
| Where does this exact string occur? | Built-in literal search |
| What does this known file do? | Built-in file reading |

Semantic discovery and symbolic analysis reinforce each other: use Semble to find likely endpoints, then Serena to verify declarations and real reference relationships. Never present a name-based text search as a reference check.

The detailed measurement history and reproduction protocol live in [BENCHMARKS.md](BENCHMARKS.md), outside the agent instructions. The product value, principles, and prioritized next steps live in [ROADMAP.md](ROADMAP.md).

## Versions and data

The pinned package version and the version a server reports over MCP are different
numbers. Both are listed because your client shows the second one.
[COMPATIBILITY.md](COMPATIBILITY.md) records which client, server, OS, and runtime
combinations are actually tested, and which are merely expected to work.

| Server | Pinned package | Reports itself as |
|---|---|---|
| Serena | `serena-agent==1.7.0` | `1.28.1` |
| Semble | `semble[mcp]==0.5.5` | `1.29.0` |

The Semble pin is load-bearing rather than cautious: the launcher overrides a private
Semble API that was renamed between 0.5.2 and 0.5.5, and the rename is invisible until
the first search. `tests/semble_api_contract.py` asserts that contract on every CI run.

### Where data is written

| Client | Embedding model | Semble index |
|---|---|---|
| Claude Code | `${CLAUDE_PLUGIN_DATA}/huggingface` | `${CLAUDE_PLUGIN_DATA}/semble-cache` |
| Codex | `~/.cache/huggingface` (default) | `~/Library/Caches/semble` on macOS, `~/.cache/semble` on Linux (default) |

Claude Code exposes a stable per-plugin data directory that survives upgrades and is
removed on uninstall, so the plugin points both caches at it. Codex's plugin cache is
version-scoped, so writing caches there would discard them on every upgrade; the
standard user cache locations are used instead. First start downloads roughly 32 MB of
embedding model.

Both servers run locally on Python `3.12`, the launcher pins `filelock==3.32.4`, and no
credentials are bundled. Network access is required when `uv` downloads packages and
when Semble downloads its embedding model. The Semble launcher serializes writes to each
on-disk index so concurrent plugin processes do not publish the same cache at the same
time.

## Resource usage

Each agent session starts its own Serena process and language server. One historical measurement on a TypeScript monorepo used roughly 856 MB across seven processes for one client. Concurrent sessions and subagents can multiply that footprint.

For a Serena-only shared alternative, start one HTTP server manually and register its URL in each client:

```bash
uvx --python 3.12 --from serena-agent==1.7.0 \
  serena start-mcp-server \
  --transport streamable-http \
  --port 9121 \
  --project "$(pwd)" \
  --enable-web-dashboard false \
  --open-web-dashboard false
```

This alternative does not install Semble or the `navigate-code` skill.

## Routing reminder hook

The plugin ships a `PreToolUse` hook that states the routing preference once per
session and then stays out of the way. It never blocks by default, because a plugin
that disables your built-in search the moment it is installed breaks legitimate
work -- reading a lockfile, searching a log -- that the routing argument says nothing
about.

| `LCN_ROUTING_HOOK` | Behavior |
|---|---|
| unset or `remind` | One short reminder on the first discovery call of a session. Always allows. |
| `off` | Silent. |
| `block` | Refuses `Grep`/`Glob` and shell search, for maintainers who have already decided. |

In `block` mode, prefix a shell command with `MCP_FALLBACK=1` to run it anyway.

## Running the checks

No credentials, model calls, or authenticated session are required.

```bash
uv run --python 3.12 --script tests/parse_config.py       # manifests and cross-references
uv run --python 3.12 --script tests/semble_api_contract.py # pinned private Semble API
python3 tests/mcp_contract.py                              # real MCP tool surface
python3 tests/hook_contract.py                             # hook nudges, never overreaches
claude plugin validate plugins/local-code-navigator --strict
claude plugin validate . --strict
```

`tests/mcp_contract.py` starts each server over stdio exactly as a coding client would
and asserts the tool surface each client is contracted to receive. It also issues a real
Semble `search`, which is the only path that reaches the launcher's index lock -- a
startup-only check would pass while exercising none of this plugin's own code. Pass
`--skip-search` to skip the index build when iterating locally.

## Repository layout

```text
.agents/plugins/marketplace.json       # Codex marketplace
.claude-plugin/marketplace.json        # Claude Code marketplace
plugins/local-code-navigator/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── .mcp.claude.json
├── .mcp.json
├── contexts/claude-balanced.yml
├── contexts/codex-balanced.yml
├── hooks/hooks.json
├── hooks/routing_reminder.py
├── scripts/start_semble.py
└── skills/navigate-code/SKILL.md
tests/                                 # manifest, MCP tool-surface, and API contracts
```

## License

This plugin is released under the [MIT License](LICENSE). Serena and Semble are separate upstream projects distributed under their own licenses.
