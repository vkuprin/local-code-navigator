# Local Code Navigator

Two things live here:

1. **A plugin** — symbol-aware and semantic code navigation for Claude Code and Codex,
   with a routing rule that decides which one, or neither, should answer a question.
2. **A benchmark harness** that measures whether a plugin like that actually helps,
   by running the same cases with it, with only its upstream defaults, and with nothing
   at all. It is reusable against any MCP setup, not just this one.

The harness is here because it failed the plugin. Read
[the measurement](#what-this-measured-including-the-part-that-failed) before installing
anything.

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

## Measuring your own MCP setup

`tests/routing_eval.py` answers a question that MCP servers generally assert rather than
demonstrate: **does this actually help, and what does it cost?**

It runs each case in up to three arms and reports the delta:

| arm | MCP servers | guidance | answers |
|---|---|---|---|
| `plugin` | yours | yours | does the whole setup help |
| `stock` | yours | upstream defaults only | does *your* guidance add anything |
| `baseline` | none | none | does any of it beat built-in tools |

The `stock` arm is the one most setups never run, and it is usually the interesting one.
Beating "no tools at all" is easy; beating the tool's own defaults is the real claim.

### Pointing it at something else

```bash
export ANTHROPIC_API_KEY=...          # `claude --bare` never reads OAuth or the keychain

uv run --python 3.12 --script tests/routing_eval.py \
  --cases path/to/your-cases.yaml \
  --repo /tmp/frozen-snapshot \
  --arms plugin,stock,baseline --runs 3 --model sonnet \
  --json results.json
```

Runs use `claude -p --bare`, which skips hooks, CLAUDE.md discovery, plugin sync and
auto-memory, so a developer's personal configuration cannot leak into a result.

### What is scored, and why separately

| metric | question |
|---|---|
| `route` | was the first substantive tool the right *kind* |
| `tool` | was the expected tool used at all |
| `evidence` | did the answer cite what it must cite |
| `claims` / `judged` | did it avoid a forbidden claim, literally and semantically |
| `files` | for mutating cases, did the edit actually land on disk |
| `calls` | how much wandering |
| `tok_in` | **how much context it burned** |
| `cost`, `wall_s` | money and wall time |

`tok_in` is the one most likely to change your mind. A tool that saves calls while
loading twenty tool schemas into context on every turn is not saving anything, and call
count cannot show that.

### Five ways this harness lied before it was fixed

Every one of these flattered the plugin, and each is now guarded. If you build something
similar, expect the same:

1. **Substring evidence checks.** `18,200` scored as wrong against `18200`.
2. **Substring claim checks.** The *ideal* answer named a decoy in order to exclude it
   and was scored as a violation. Semantic assertions need a judge.
3. **Tight `--max-turns`.** Truncated the baseline mid-task, and truncation reported as
   an error — missing data dressed up as a loss.
4. **Broken token accounting.** `usage.input_tokens` counts only the uncached remainder
   and reported 7 tokens for runs that consumed 49,000. The real totals are in
   `modelUsage`. This one hid the single most important result.
5. **A moving corpus.** The first real-repository run measured a live checkout while
   another session edited it; the symbol under test moved from line 920 to 926 mid-run.
   The runner now fingerprints the corpus and refuses to publish if it changed. Snapshot
   before you measure.

A sixth is worth stating because it is not a bug: on cases where only one arm has the
tool, that arm's routing score is arithmetic, not judgment. Compare arms on calls,
context and correctness.

### Writing cases

`evals/cases.yaml` (synthetic fixture) and `evals/cases-sitespy.yaml` (real snapshot)
are worked examples. A case declares the prompt, the expected route, the evidence it
must cite, forbidden claims, and — for refactoring cases — assertions checked against
the files afterwards, because a rename that reports success without editing anything is
the failure worth catching. Mutating cases run against a throwaway copy.

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

## Tests

Everything here runs without credentials, model calls, or an authenticated session,
except the routing evaluation, which necessarily spends tokens.

| file | what it guards |
|---|---|
| `tests/parse_config.py` | every JSON/YAML manifest parses; paths written inside MCP configs exist; both marketplaces agree; hook scripts exist and are executable; the two Semble pins agree; **instruction footprint stays under a declared ceiling** |
| `tests/mcp_contract.py` | both servers really start over stdio and expose the contracted tool surface — 21 tools under the Claude context, 23 under Codex, the six client-owned tools excluded in both |
| `tests/semble_api_contract.py` | the private Semble API the launcher overrides still exists with the same signature |
| `tests/hook_contract.py` | the routing hook advises without blocking, does not overreach onto ordinary commands, honours the `MCP_FALLBACK=1` escape hatch, and survives malformed input |
| `tests/concurrent_index.py` | N builders racing one cold cache: search success, swallowed cache-write failures, and whether the cache still parses |
| `tests/routing_eval.py` | whether the routing guidance changes behaviour, against `stock` and `baseline` arms |

```bash
uv run --python 3.12 --script tests/parse_config.py
uv run --python 3.12 --script tests/semble_api_contract.py
python3 tests/mcp_contract.py            # add --skip-search to skip the index build
python3 tests/hook_contract.py
python3 tests/concurrent_index.py --procs 4 --trials 1
claude plugin validate plugins/local-code-navigator --strict
claude plugin validate . --strict
```

CI runs all of these on ubuntu and macOS, plus a weekly schedule — upstream releases
rather than commits here are what break the pinned private API.

Two of these exist because a cheaper version of them passed while testing nothing.
`mcp_contract.py` issues a real `search`, because `tools/list` alone never builds an
index and therefore never reaches the launcher's lock. `semble_api_contract.py` checks
the *signature*, because Python resolves a base class at import time: under the wrong
Semble version the server starts cleanly and only fails on the first search.

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
tests/                                 # contracts, concurrency, and the routing benchmark
evals/
├── cases.yaml                         # routing cases over the synthetic fixture
├── cases-sitespy.yaml                 # routing cases over a real 330-file snapshot
├── fixture/                           # redistributable corpus, exact ground truth
└── results/                           # raw per-run data behind every published number
```

## License

This plugin is released under the [MIT License](LICENSE). Serena and Semble are separate upstream projects distributed under their own licenses.
