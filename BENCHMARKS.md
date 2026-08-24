# Navigation benchmarks

## What this plugin does and does not buy you

Measured on the fixture in [`evals/`](evals/), 3 trials per case per arm, 30 runs,
`claude -p --bare` with `haiku`, $0.44:

| | route | tool used | evidence | claims | judged | budget | mean calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| plugin | 93% | 100% | 100% | 100% | 100% | 100% | **1.9** |
| baseline | 40% | 60% | 100% | 100% | 100% | 80% | **5.2** |

**Correctness was identical. Both arms scored 100% on evidence, forbidden claims, and
semantically judged claims.** On this fixture the plugin did not make a single answer
more correct than built-in tools did.

**The difference is how much work it took to get there:** 1.9 tool calls against 5.2,
with the gap concentrated exactly where the routing argument predicts.

| Case | plugin calls | baseline calls |
|---|---:|---:|
| reference check with a same-name decoy | 2.0 | 13.3 |
| behavior described, name unknown | 2.0 | 3.0 |
| implementation trace across files | 3.7 | 7.7 |
| reasoning about one known file | 1.0 | 1.0 |
| literal string search | 1.0 | 1.0 |

The last two rows matter as much as the first. They are the over-routing check: a
plugin that dragged a single-known-file question through symbolic tooling would be
worse than no plugin. It did not — both arms took exactly one call, and the plugin
chose a built-in tool 100% of the time when a built-in tool was right.

## How to read the routing columns

`route` and `tool used` look like large wins and mostly are not. On cases expecting
Serena or Semble the baseline scores 0% **by construction** — it has no such tools to
choose. Those columns are a plugin-arm diagnostic, not a head-to-head result. The
honest comparisons are mean calls, the correctness columns, and routing on the two
built-in cases.

## Reproducing this

```bash
export ANTHROPIC_API_KEY=...
uv run --python 3.12 --script tests/routing_eval.py --runs 3 --model haiku \
  --json evals/results/routing-haiku-3runs.json
```

Raw per-run results, including tool sequences and answers, are in
[`evals/results/`](evals/results/). The corpus is checked into this repository rather
than pinned from an external project, so the ground truth is exact and the suite is
redistributable. [`evals/README.md`](evals/README.md) documents the scoring model and
its caveats — read the caveats before quoting a number.

## Not yet measured

Issue #6 also asks for latency, peak RSS, index size on disk, and cold-versus-warm
cache behavior. None of those are collected yet, and no claim is made about them here.
The one number available: first Semble start downloads roughly 32 MB of embedding model.

## Historical results

The figures below came from a private TypeScript monorepo and predate the public suite.
They are kept because they motivated the original routing boundary, not because they are
reproducible — the corpus is not redistributable and the exact counts cannot be
reconstructed from this repository. **Do not cite them as evidence.**

| Task | Symbol-aware route | Built-in route | Result |
|---|---:|---:|---|
| Reference check for an ambiguous symbol | 2 tool calls | 19 tool calls | Same substantive conclusion |
| Read and reason about known code | 6 tool calls | 4 tool calls | Built-ins produced the more accurate answer |

The public suite reproduced the shape of the first row on its own fixture (2.0 against
13.3 calls, same conclusion). It has not reproduced the second row: on the
known-file case both arms took one call and both were correct.

## Protocol notes

Tool versions, repository size, language-server state, model choice, prompts, and cache
warmth all affect these numbers. Any new public claim should ship with the fixture or
pinned revision it was measured on, the raw traces, and enough trials to show variance —
a single run of the reference case has been observed anywhere between 1 and 13 calls.
