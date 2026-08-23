# Local Code Navigator

A cross-agent plugin that combines semantic retrieval with language-server-backed symbol intelligence for Claude Code and Codex.

- [Serena](https://github.com/oraios/serena) provides symbol lookup, references, diagnostics, and symbolic edits.
- [Semble](https://github.com/MinishLab/semble) provides semantic search when you know the behavior but not the symbol name.
- The lazy `navigate-code` skill routes work between those MCP servers and each coding agent's built-in file tools.

Installing the plugin contributes both MCP servers and the matching guidance. Removing it removes both, so the skill never advertises tools the user did not install.

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

The detailed measurement history and reproduction protocol live in [BENCHMARKS.md](BENCHMARKS.md), outside the agent instructions.

## Versions and data

- Serena: `1.7.0`
- Semble: `0.5.5`
- File-lock helper: `3.32.4`
- Python runtime: `3.12`
- Credentials bundled: none

Both servers run locally. Network access is required when `uv` downloads packages and when Semble downloads its embedding model. The Semble launcher serializes writes to each on-disk index so concurrent plugin processes do not publish the same cache at the same time.

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
├── scripts/start_semble.py
└── skills/navigate-code/SKILL.md
```

## License

This plugin is released under the [MIT License](LICENSE). Serena and Semble are separate upstream projects distributed under their own licenses.
