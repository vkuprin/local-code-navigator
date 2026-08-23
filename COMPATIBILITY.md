# Compatibility

What has actually been tested, and what has not. A combination is listed as tested only
if a check was run and recorded — "should work" is a separate column on purpose.

Legend:

- **CI** — asserted on every pull request by [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
- **Verified** — exercised by hand, once, on the version shown
- **Expected** — no reason to think it fails, never run
- **Unsupported** — not tested and not maintained; bug reports welcome but unowned

## Plugin 1.1.0

### Coding clients

| Client | Version | Install | MCP servers start | Tool surface asserted | Status |
|---|---|---|---|---|---|
| Claude Code | 2.1.241 | manifest validated | yes | yes, 21 tools | CI + Verified |
| Codex CLI | 0.149.0 | yes, from a local marketplace | yes | yes, 23 tools | Verified |

Claude Code manifest validation runs in CI via `claude plugin validate --strict` for
both the plugin and the marketplace. The Serena and Semble tool surfaces are asserted in
CI for both contexts by `tests/mcp_contract.py`.

**Not yet verified:** installing into Claude Code from the *public* marketplace on a
machine that has no direct `serena`/`semble` MCP registration to shadow it. Until that
runs, `${CLAUDE_PLUGIN_DATA}` expansion and the
`mcp-logs-plugin-local-code-navigator-*` log path are expected rather than verified.
Tracked in issue #5.

### MCP servers

| Server | Pinned package | Reports itself as | Notes |
|---|---|---|---|
| Serena | `serena-agent==1.7.0` | `1.28.1` | Latest on PyPI as of 2026-08-24 |
| Semble | `semble[mcp]==0.5.5` | `1.29.0` | Latest on PyPI as of 2026-08-24 |

The two numbers differ because the PyPI package version and the version the server
announces over MCP are separate namespaces. Your client shows the second one.

**The Semble pin is load-bearing.** `scripts/start_semble.py` overrides
`_IndexCache._build_index`, which did not exist under 0.5.5's predecessor: 0.5.2 named
it `_build_and_cache_index`. Python resolves the base class at import time, so a
mismatched version still starts cleanly and only fails on the first search.
`tests/semble_api_contract.py` asserts the shape in CI, including on a weekly schedule
so upstream drift surfaces without waiting for a user to hit it. See issue #2.

### Platforms

| OS | Arch | Status | How |
|---|---|---|---|
| macOS 15.6.1 | arm64 | Verified | local runs, both clients |
| macOS (latest runner) | arm64 | CI | `tests/mcp_contract.py` |
| Ubuntu (latest runner) | x86_64 | CI | full suite |
| Linux, other distributions | x86_64 | Expected | — |
| macOS | x86_64 | Expected | — |
| Windows | any | Unsupported | no maintainer |

### Runtime

| Component | Version | Status |
|---|---|---|
| Python | 3.12 (`>=3.12,<3.13`) | CI |
| uv / uvx | 0.11.30 | Verified |
| `filelock` | 3.32.4 | CI |

Python is constrained to 3.12 by `scripts/start_semble.py`. Serena is launched with
`uvx --python 3.12`, so the plugin does not use whatever Python happens to be on
`PATH`.

## Support policy

Only the latest released plugin version is supported, matching [`SECURITY.md`](SECURITY.md).
Upstream Serena and Semble security advisories are the upstream projects' to publish;
this repository pins exact versions, so a fix there requires a release here.

## Updating this file

Update it in the same change that alters a pin, a manifest, or a supported client, and
move a row from Expected to CI or Verified only alongside the check that justifies it.
