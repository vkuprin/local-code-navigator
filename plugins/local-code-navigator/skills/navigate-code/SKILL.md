---
name: navigate-code
description: Navigate unfamiliar code with semantic search, symbol intelligence, and built-in file tools. Use for implementation discovery, architecture tracing, reference checks, renames, or symbolic edits when Semble and Serena are available.
---

# Navigate code with Semble and Serena

Choose the narrowest route that matches the question.

## Routing

1. Use Semble `search` when the user describes behavior or architecture but does not know the symbol name. Pass the current repository root as `repo`. Start with `top_k=5` and compact snippets; expand results only when the first response lacks enough evidence.
2. Semble defaults to code. Set `content` to `docs`, `config`, or `all` only when the question needs those sources.
3. Use Semble `find_related` when a known result should lead to similar implementations.
4. Use Serena for symbol and relationship questions: overviews, symbol bodies, declarations, implementations, real references, diagnostics, renames, and whole-symbol edits.
5. Use the coding agent's built-in file tools for literal text, file discovery, reading and reasoning about known files, and small inline changes.

For architecture tracing, start with Semble to locate likely endpoints, then use Serena references to confirm actual relationships. Never report a name-based text search as a semantic reference check.

## Project setup

- Use the coding agent's current workspace or repository root for Semble's `repo` argument.
- Some clients start Serena with that project already active. If Serena reports that no project is active and exposes `activate_project`, activate the current repository once. Do not call it when a project is already active or when the tool is unavailable.

## Serena constraints

- Serena locations are 0-based. Add 1 before citing a Serena line to the user. Do not adjust Semble results, which are already 1-based.
- Verify arithmetic and aggregates yourself. Structured tool output does not guarantee correct derived totals.
- Fewer tool calls improve efficiency but do not independently prove correctness.

## Where each route wins

Use Serena for reference checks, implementations, and renames. A symbolic reference
lookup answers "who actually calls this" directly, where a name-based search returns
every same-name occurrence and leaves you to sort real references from coincidence.

Use built-in file reading and literal search for reasoning about a file you can already
name. Routing those through a symbolic tool adds calls without adding certainty. Serena
is for code intelligence, not for every code question.

Measurement history and the reproduction protocol live in the repository's
`BENCHMARKS.md`, not in these reusable agent instructions.
