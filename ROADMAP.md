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

## What is measured

The routing boundary is no longer an assertion. Measured over the public fixture in
[`evals/`](evals/), 45 runs across three arms:

| arm | route | evidence | mean calls |
|---|---:|---:|---:|
| this plugin | 93% | 100% | 2.4 |
| Serena's stock context, no guidance | 60% | 100% | 3.5 |
| no MCP servers at all | 40% | 100% | 4.9 |

Correctness was identical everywhere. **The plugin does not make answers better; it
reaches the same answers in fewer steps** — 3.3 calls against 15.0 on a reference check
with an ambiguous symbol, and exactly 1.0 against 1.0 where a built-in tool is the right
answer. That last number is the one that justifies the project: a router that dragged
simple questions through symbolic tooling would be worse than nothing.

See [BENCHMARKS.md](BENCHMARKS.md) for the caveats, which matter more than the headline.

## Remaining before release

1. [Verify the Claude Code install from the public marketplace](https://github.com/vkuprin/local-code-navigator/issues/5) — the only real blocker. The plugin has never run *as a plugin* on Claude Code, because direct MCP registrations shadow it.
2. [Report a Codex arm for the routing cases](https://github.com/vkuprin/local-code-navigator/issues/7).
3. [Add process and cache-state metrics](https://github.com/vkuprin/local-code-navigator/issues/6).
4. [Report the non-atomic index write upstream](https://github.com/vkuprin/local-code-navigator/issues/2).

Delivered: a [public corpus and harness](https://github.com/vkuprin/local-code-navigator/issues/1), [CI over both plugin formats and MCP startup](https://github.com/vkuprin/local-code-navigator/issues/4), and a [tested compatibility matrix](https://github.com/vkuprin/local-code-navigator/issues/3).

## Not goals

- Replacing ordinary file reading or literal search with MCP calls.
- Claiming that semantic or symbolic tooling is cheaper or more accurate for every task.
- Building a general-purpose coding-agent framework.
- Hiding runtime downloads, resource costs, cache behavior, or compatibility constraints.
