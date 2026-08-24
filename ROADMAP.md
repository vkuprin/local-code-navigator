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

The routing claim was tested and **did not hold on a real repository**. 108 runs on
`sonnet`, two corpora, three arms:

| corpus | model | plugin calls | baseline calls | plugin context | baseline context |
|---|---|---:|---:|---:|---:|
| 9-file fixture | haiku | 1.9 | 5.2 | — | — |
| 9-file fixture | sonnet | 3.8 | 5.3 | — | — |
| 330-file snapshot | sonnet | 3.4 | 3.2 | 1,079,404 | 212,886 |

On real code the plugin costs **5.1x more context**, is more expensive, and answered
its own flagship reference case correctly in 1 of 3 runs. Full numbers and the
reproduction in [BENCHMARKS.md](BENCHMARKS.md).

The one thing that survived is symbolic renaming. Everything else the project was built
on is not supported by its own measurements.

## What this repository is now for

The harness outlived the claim it was built to support, and it is the more useful
artifact. `tests/routing_eval.py` measures any MCP setup against three arms — with your
guidance, with the tool's upstream defaults, and with no MCP at all — and reports
routing, correctness, context, cost and wall time separately.

The middle arm is the point. Beating "no tools" is easy. Beating the tool's own defaults
is the claim worth making, and it is the one almost nobody runs.

## Open

1. [Verify the Claude Code install from the public marketplace](https://github.com/vkuprin/local-code-navigator/issues/5).
2. [Report a Codex arm for the routing cases](https://github.com/vkuprin/local-code-navigator/issues/7).
3. [Add process and cache-state metrics](https://github.com/vkuprin/local-code-navigator/issues/6).
4. [Report the non-atomic index write upstream](https://github.com/vkuprin/local-code-navigator/issues/2).

Delivered: a [public corpus and harness](https://github.com/vkuprin/local-code-navigator/issues/1), [CI over both plugin formats and MCP startup](https://github.com/vkuprin/local-code-navigator/issues/4), and a [tested compatibility matrix](https://github.com/vkuprin/local-code-navigator/issues/3).

## Not goals

- Replacing ordinary file reading or literal search with MCP calls.
- Claiming that semantic or symbolic tooling is cheaper or more accurate for every task.
- Building a general-purpose coding-agent framework.
- Hiding runtime downloads, resource costs, cache behavior, or compatibility constraints.
