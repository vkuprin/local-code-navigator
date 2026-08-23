# Local Code Navigator for Claude Code

A portable Claude Code plugin powered by two complementary local code-navigation tools:

- [Serena](https://github.com/oraios/serena) for symbol lookup, references, diagnostics, and symbolic edits.
- [Semble](https://github.com/MinishLab/semble) for semantic search when you know the behavior but not the symbol name.
- A lazy `navigate-code` skill that routes work between them and Claude Code's built-in Read, Grep, and Glob tools.

Installing the plugin contributes both MCP servers and the skill. Uninstalling it removes them together, so users without the optional tools do not carry stale navigation guidance.

## Install

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) first so `uvx` is available on `PATH`, then run:

```bash
claude plugin marketplace add vkuprin/serena-semble-claude-plugin
claude plugin install serena-semble@vkuprin-tools --scope user
```

The first launch downloads the pinned Serena and Semble packages. The first Semble query also downloads its compact embedding model.

If either server is already registered directly, remove the duplicate before starting a plugin-enabled session:

```bash
claude mcp remove serena --scope user
claude mcp remove semble --scope user
```

Verify the installation:

```bash
claude plugin details serena-semble@vkuprin-tools
claude mcp list
```

## Update

```bash
claude plugin marketplace update vkuprin-tools
claude plugin update serena-semble@vkuprin-tools --scope user
```

## Uninstall

```bash
claude plugin uninstall serena-semble@vkuprin-tools --scope user
```

The final uninstall removes the plugin data directory, including Semble's downloaded model and indexes. Pass `--keep-data` to preserve it.

## Why this combination?

The tools solve different navigation problems:

| Question | Best first tool |
|---|---|
| "Where is behavior like this implemented?" | Semble semantic search |
| "What is this symbol and who references it?" | Serena symbol intelligence |
| "Where does this exact string occur?" | Claude Code Grep |
| "What does this known file do?" | Claude Code Read |

In one benchmark on an ambiguous `Text` symbol in `packages/ui-mobile`, Serena completed a reference check in 2 tool calls versus 19 with name-based grep. For read-and-reason work, built-in Read plus Grep was both cheaper and more accurate: 4 calls versus 6. The skill encodes that measured boundary instead of forcing every code question through an MCP.

## Versions and data

- Serena: `1.7.0`
- Semble: `0.5.2`
- Python runtime selected by `uvx`: `3.12`
- Semble model and indexes: `${CLAUDE_PLUGIN_DATA}`
- Credentials bundled: none

Both MCP servers run locally. Network access is still required when `uvx` downloads packages and when Semble downloads its embedding model. Review the upstream Serena and Semble projects for their complete behavior and security policies.

## Resource usage

Each Claude MCP client starts its own Serena process and language server. One measurement on a TypeScript monorepo used roughly 856 MB across seven processes for one client. Multiple Claude sessions and subagents can multiply that footprint.

For a shared alternative, run one Serena HTTP server manually and register its URL with each client instead of installing this plugin:

```bash
serena start-mcp-server \
  --transport streamable-http \
  --port 9121 \
  --project "$(pwd)" \
  --enable-web-dashboard false \
  --open-web-dashboard false
```

## Repository layout

```text
.claude-plugin/marketplace.json
plugins/serena-semble/
├── .claude-plugin/plugin.json
├── .mcp.json
├── README.md
└── skills/navigate-code/SKILL.md
```

## License

This plugin is released under the [MIT License](LICENSE). Serena and Semble are separate upstream projects distributed under their own licenses.
