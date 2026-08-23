# Routing evaluation

Answers one question with evidence rather than assertion: **does this plugin's routing
guidance actually change how a coding agent navigates code, and for the better?**

That question decides whether the custom Serena contexts earn their keep. Serena's own
stock `claude-code` context excludes the same six client-owned tools this plugin
excludes, so the only real difference is prompt wording -- stock says "Read is
FORBIDDEN for discovery", this plugin says "choose the narrowest tool that matches the
question". One of those is better. This measures which.

## Layout

```text
evals/cases.yaml      case definitions: prompt, expected route, evidence, rubric
evals/fixture/        a small synthetic codebase, written here so it is redistributable
evals/results/        run output (JSON)
```

## Running it

```bash
export ANTHROPIC_API_KEY=...   # `claude --bare` never reads OAuth or the keychain
uv run --python 3.12 --script tests/routing_eval.py --runs 3 --model haiku
```

Useful flags: `--case <substring>` to run one case, `--no-judge` to skip semantic
grading, `--max-cost-usd` to cap spend, `--json <path>` to keep full results.

## What is scored, and why separately

| Score | Question |
|---|---|
| route | Was the first substantive tool the right *kind* for this question? |
| evidence | Did the answer cite what it must cite? |
| claims | Did it avoid a literal forbidden string? |
| judged | Did it avoid a forbidden *claim*, graded semantically? |
| budget | Did it get there without wandering? |

These fail independently. An answer can be correct by luck after six wrong turns, and
an answer can route perfectly and still cite nothing. Collapsing them into one number
hides exactly the information that would tell you which rule to change.

Every case runs in two arms -- `plugin` (the plugin's MCP config plus its guidance) and
`baseline` (built-in tools only) -- so each score is reported as a delta, not an
absolute. A plugin that matches the baseline is not earning its context budget.

## Read `route` as a diagnostic, not as a scoreboard

On cases that expect `serena` or `semble`, the baseline arm scores 0% on `route` **by
construction** -- it has no such tools to choose. A headline like "80% vs 46% routing"
is therefore mostly restating which arm has MCP servers installed. It says nothing
about judgment.

The comparisons that do carry information:

- **calls** -- both arms can reach the answer; how much wandering did it take
- **evidence** and **judged** -- was the answer actually right, and did it avoid the
  claim it must not make
- **route on the `builtin` cases** -- this is the over-routing check, and it is the one
  place a plugin can genuinely *lose*. A plugin that drags a single-known-file question
  through symbolic tooling is worse than no plugin.

`tool` (did the expected tool get used at all) is reported next to `route` (was it used
*first*) because they diverge for good reasons. Opening the file that names a symbol
before looking up its references is sensible, and first-call-only scoring records that
as a miss.

## Three things to know before trusting a number

**Semantic assertions need a judge, not a substring.** The reference-check case has a
same-name decoy, `LegacyBiller.charge`. Presenting it as a reference is the failure the
skill most wants to prevent -- but *naming it in order to exclude it* is correct. A
substring check scores the ideal answer as a violation, which it did during development
until the grader replaced it. `judge_assertions` exist for this class of check.

**One run is noise.** The reference-check case has been observed taking 1 call and 13
calls on the same arm, and flipping which arm cited better evidence. Use `--runs 3` or
more and read the aggregate; a single trial cannot distinguish a routing regression
from model variance. A single run once showed the baseline making a prohibited claim
where the plugin did not; across three runs both arms were clean. The single run was
the outlier, and reporting it would have overstated the plugin.

**A truncated run is missing data, not a loss.** `--max-turns` is set to double the
case budget plus headroom, because the baseline arm legitimately needs more calls and
an arm cut off mid-task reports as an error. Budget adherence is scored separately from
being allowed to finish.

## Fidelity caveat

The plugin arm injects the skill body via `--append-system-prompt`, because `--bare`
does not sync installed plugins. A real install exposes the skill lazily instead, so
this arm sees the guidance more strongly than a real session would. It answers "does
the guidance change routing", which is the question here, but it is not a substitute
for `claude plugin eval` once that leaves early access.
