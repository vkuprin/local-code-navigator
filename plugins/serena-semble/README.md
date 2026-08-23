# Serena + Semble Claude Code plugin

Optional, all-or-nothing code-navigation tooling for Claude Code. Installing the plugin contributes:

- Serena 1.7.0 for symbols, references, diagnostics, and symbolic edits.
- Semble 0.5.2 for local semantic search across code, docs, and configuration.
- The lazy `navigate-code` skill with measured routing guidance.

Uninstalling removes both MCP registrations and the skill. No credentials are bundled.

## Prerequisite

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) so `uvx` is on `PATH`. The plugin pins Python 3.12 and both tool versions. `uvx` downloads the tools on first start, and the first Semble query downloads its compact embedding model. Semble's model and indexes live under `${CLAUDE_PLUGIN_DATA}`, so they survive plugin upgrades and are removed on uninstall unless `--keep-data` is used.

## Install

```bash
claude plugin marketplace add vkuprin/serena-semble-claude-plugin
claude plugin install serena-semble@vkuprin-tools --scope user
```

If Serena or Semble is already registered directly, remove those duplicate registrations before starting a plugin-enabled session:

```bash
claude mcp remove serena --scope user
claude mcp remove semble --scope user
```

Verify with:

```bash
claude plugin details serena-semble@vkuprin-tools
claude mcp list
```

## Update and uninstall

The manifest version must be bumped for each release.

```bash
claude plugin marketplace update vkuprin-tools
claude plugin update serena-semble@vkuprin-tools --scope user

claude plugin uninstall serena-semble@vkuprin-tools --scope user
```

By default the final uninstall also removes `${CLAUDE_PLUGIN_DATA}`, including Semble's model and indexes. Add `--keep-data` to retain them.

## Routing boundary

- Use Semble for behavior and architecture searches when the symbol name is unknown.
- Use Serena for symbols, references, diagnostics, and atomic symbolic edits.
- Use Claude Code's Read, Grep, and Glob for known-file reasoning, literal text, and file discovery.

On one ambiguous-symbol benchmark, Serena reference lookup took 2 tool calls versus 19 with name grep. For read-and-reason work, Read plus Grep took 4 calls versus 6 and produced the more accurate answer. The included skill preserves this boundary.

## Runtime cost

Each Claude MCP client starts its own Serena and language-server processes. A measurement on a TypeScript monorepo used about 856 MB across seven processes for one client; concurrent desktop sessions and subagents multiply that footprint.

For a shared alternative, do not install this plugin. Start one Serena HTTP server manually and register its URL with each client:

```bash
serena start-mcp-server \
  --transport streamable-http \
  --port 9121 \
  --project "$(pwd)" \
  --enable-web-dashboard false \
  --open-web-dashboard false
```

The shared server avoids duplicate language servers but must be started and monitored separately.

