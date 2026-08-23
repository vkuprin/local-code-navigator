# Changelog

All notable changes to this project will be documented here.

## Unreleased

- Add `contexts/codex-balanced.yml` so Codex and Claude Code exclude the same
  client-owned tools instead of receiving mirror-image tool surfaces.
- Point the Codex MCP config at the balanced context and document that its relative
  paths resolve against the plugin root.
- Add `tests/` with three checks that need no credentials: manifest and
  cross-reference parsing, the pinned private Semble API contract, and a real MCP
  tool-surface assertion that includes an index-building `search`.
- Add CI covering both plugin manifests, both Serena contexts, the Semble launcher,
  and weekly upstream drift.
- Document the difference between each server's pinned package version and the
  version it reports over MCP, and where each client writes model and index caches.
- Drop routing claims that rested on an unreproducible private benchmark.
- Ignore `.serena/`, which Serena writes wherever it activates a project.

## 1.1.0 - 2026-08-24

- Rename the public package and install ID to `Local Code Navigator` / `local-code-navigator`.
- Add a Codex marketplace and plugin manifest alongside Claude Code support.
- Remove project-specific benchmark examples from the reusable skill and main README.
- Move measurement history and a reproduction protocol to `BENCHMARKS.md`.
- Align Serena's Claude Code context with the measured routing boundary.
- Upgrade Semble to 0.5.5 for per-query content selection and serialize index-cache writes.
- Document client reload behavior, scope-safe duplicate removal, and the pinned shared Serena command.

## 1.0.1 - 2026-08-24

- Use the neutral `Local Code Navigator` display name for directory compatibility.

## 1.0.0 - 2026-08-24

- Package Serena 1.7.0 and Semble 0.5.2 as Claude Code MCP servers.
- Add the lazy `navigate-code` skill with benchmark-informed routing guidance.
- Store Semble models and indexes in Claude's plugin data directory.
