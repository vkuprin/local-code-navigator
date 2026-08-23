# Roadmap

## Why this project exists

Code navigation is not one problem. A developer may know the behavior they need but not its name, may need every real reference to a symbol, or may simply need an exact string in a known file. Those questions need different retrieval strategies.

Local Code Navigator packages a small routing layer with the tools it describes:

- Semble discovers code by meaning when names and paths are unknown.
- Serena resolves symbols, implementations, references, diagnostics, and structured edits.
- The coding client's built-in tools remain the efficient path for literal search and focused reading.

Shipping the MCP servers and skill together is part of the value. Installation adds the capability and its guidance; removal removes both. Developers without the optional tooling do not pay for always-on instructions that cannot work.

## Product principles

- **Match the route to the question.** No tool should become the default for every code task.
- **Measure before prescribing.** Routing rules need repeatable evidence, not intuition or vendor claims.
- **Treat efficiency and correctness separately.** Fewer calls are useful only when the answer remains sound.
- **Keep agent context small.** Add skill instructions only for demonstrated, recurring failures.
- **Stay local and inspectable.** Be explicit about downloads, caches, subprocesses, resource use, and upstream dependencies.
- **Keep one behavioral contract across clients.** Claude Code and Codex may need different manifests, but the navigation model should not drift.

## Near-term priorities

1. [Make the benchmark claims publicly reproducible](https://github.com/vkuprin/local-code-navigator/issues/1).
2. [Turn the routing boundary into regression cases for the skill](https://github.com/vkuprin/local-code-navigator/issues/7).
3. [Validate both plugin formats and MCP startup continuously](https://github.com/vkuprin/local-code-navigator/issues/4).
4. [Test installation from clean macOS and Linux environments](https://github.com/vkuprin/local-code-navigator/issues/5).
5. [Report accuracy, cost, latency, memory, and cold-versus-warm cache behavior](https://github.com/vkuprin/local-code-navigator/issues/6).
6. [Publish a tested compatibility matrix](https://github.com/vkuprin/local-code-navigator/issues/3).
7. [Replace the pinned Semble private-API cache hook with a stable upstream contract](https://github.com/vkuprin/local-code-navigator/issues/2).

The implementation backlog is tracked in GitHub issues. This file describes the product direction; individual issues own scope, acceptance criteria, dependencies, and trade-offs.

## Not goals

- Replacing ordinary file reading or literal search with MCP calls.
- Claiming that semantic or symbolic tooling is cheaper or more accurate for every task.
- Building a general-purpose coding-agent framework.
- Hiding runtime downloads, resource costs, cache behavior, or compatibility constraints.
