# Navigation benchmarks

## Headline: the fixture result did not survive a real repository

Everything below the next heading was measured on a nine-file synthetic fixture with
`haiku`. It is kept because it is real, and because the gap between it and the numbers
here is the most useful thing in this file.

Frozen 330-file snapshot of a production codebase, `sonnet`, 6 cases x 3 arms x 3 runs,
54 runs, 0 errors, $1.14:

| arm | route | correctness | judged | mean calls | context | cost |
|---|---:|---:|---:|---:|---:|---:|
| plugin | 67% | 89% | 33% | 3.4 | 1,079,404 | $0.0257 |
| stock | 50% | 100% | 100% | 3.0 | 812,169 | $0.0214 |
| baseline | 33% | 100% | 100% | 3.2 | 212,886 | $0.0162 |

### Context cost, per case

The plugin is more expensive on every single case, including the one designed to be
its best.

| case | plugin | baseline | ratio |
|---|---:|---:|---:|
| reference check, 4 same-name decoys | 57,620 | 18,733 | 3.1x |
| behavior described, name unknown | 125,304 | 14,910 | 8.4x |
| reasoning about one known file | 37,337 | 7,227 | 5.2x |
| literal string search | 28,475 | 4,098 | 6.9x |
| 10-line symbol in a 1276-line file | 49,174 | 9,565 | 5.1x |
| rename with a same-prefix trap | 61,891 | 16,429 | 3.8x |

The large-file case was built specifically to favour symbolic navigation: a 10-line
function inside 18k tokens of source, where reading the file whole should lose badly.
It lost anyway. Tool schemas for 21 Serena tools and 2 Semble tools enter context every
turn, and that fixed overhead is larger than the variable saving.

### The correctness regression

The plugin arm answered the reference case correctly in 1 of 3 runs. The two failures
both reported line 925 where the answer is 926.

Serena reports 0-based lines and `SKILL.md` instructs the agent to add one. In the
failing runs the agent applied that correction to the definition and omitted it for the
reference **within the same answer** — one run even prints "(0-based 1190)" beside a
correct 1191 and then gives a raw 925 for the call site. A literal text search reports
1-based lines and cannot produce this class of error; both other arms scored 100%.

This reproduced across two independent runs on two different corpora. An earlier
retraction of this finding, on the grounds that it looked like variance, was wrong.

### Where the advantage went

| corpus | model | plugin | baseline | ratio |
|---|---|---:|---:|---:|
| 9-file fixture | haiku | 1.9 | 5.2 | 2.7x |
| 9-file fixture | sonnet | 3.8 | 5.3 | 1.4x |
| 330-file snapshot | sonnet | 3.4 | 3.2 | 0.9x |

Both variables matter. A stronger model narrows the gap on the same corpus, and a
realistic corpus closes it. Neither alone explains the result, which is why both were
measured separately.

### What survived

Symbolic renaming. On the fixture it took 6.3 calls against the baseline's 18.3 and
cost $0.038 against $0.089. On the real repository the same case narrowed to 4.0 calls
against 5.3, with the baseline still cheaper overall. This is the one place where the
symbolic route does something text tools handle badly, and it is a narrower claim than
the project was built on.

### Reproducing

```bash
export ANTHROPIC_API_KEY=...
# Snapshot first. Never point --repo at a working tree: an earlier attempt did, another
# session edited the file mid-run, the symbol moved from line 920 to 926, and the whole
# measurement had to be thrown away.
cp -R <path>/changedetectionio /tmp/lcn-corpus/changedetectionio
uv run --python 3.12 --script tests/routing_eval.py \
  --cases evals/cases-sitespy.yaml --repo /tmp/lcn-corpus/changedetectionio \
  --allow-mutating --arms plugin,stock,baseline --runs 3 --model sonnet
```

---

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

## Does the custom Serena context earn its keep?

This is the question that decides whether `contexts/claude-balanced.yml` should exist.
Serena ships its own `claude-code` context that excludes the identical six tools, so
the only difference between them is prompt wording: Serena's says "Read is FORBIDDEN
for discovery", this plugin's says to choose the narrowest tool that fits the question.

Three arms, 45 runs, 3 trials per case per arm, $0.63:

| arm | route | tool used | evidence | claims | judged | mean calls |
|---|---:|---:|---:|---:|---:|---:|
| plugin — this plugin's context + guidance | **93%** | 100% | 100% | 100% | 100% | **2.4** |
| stock — Serena's own context, no guidance | 60% | 100% | 100% | 100% | 100% | 3.5 |
| baseline — no MCP servers | 40% | 60% | 100% | 100% | 100% | 4.9 |

Mean tool calls per case:

| Case | plugin | stock | baseline |
|---|---:|---:|---:|
| reference check with a same-name decoy | **3.3** | 7.7 | 15.0 |
| behavior described, name unknown | **2.0** | 3.3 | 2.3 |
| implementation trace across files | 4.7 | **4.3** | 5.0 |
| reasoning about one known file | 1.0 | 1.0 | 1.0 |
| literal string search | 1.0 | 1.0 | 1.0 |

**Verdict: keep the custom context.** Against stock it routes correctly 93% of the time
versus 60%, and reaches the same answers in 2.4 calls versus 3.5 — less than half the
calls on the reference case. Unlike the baseline's zeros, stock's routing misses are
genuine judgment differences: it has exactly the same tools available and chose
differently.

Correctness was identical across all three arms on every case. Nothing here says the
plugin makes answers better. It says the same answers cost less.

Two honest limits on that verdict. The `plugin` arm carries **both** the custom context
and the navigate-code guidance, so 93% against 60% is their combined effect and this
does not isolate the context alone — separating them needs a fourth arm. And on
implementation tracing stock was marginally cheaper (4.3 against 4.7), so the win is not
uniform across question types.

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
