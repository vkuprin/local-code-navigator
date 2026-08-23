# Navigation benchmark notes

The routing guidance was informed by a small historical evaluation on a private TypeScript monorepo. Project names, paths, and symbols are intentionally omitted from the public plugin because they are benchmark provenance, not reusable agent instructions.

## Historical results

| Task | Symbol-aware route | Built-in route | Result |
|---|---:|---:|---|
| Reference check for an ambiguous symbol | 2 tool calls | 19 tool calls | Same substantive conclusion |
| Read and reason about known code | 6 tool calls | 4 tool calls | Built-ins produced the more accurate answer |

These figures establish a routing boundary, not a universal performance claim. Tool versions, repository size, language-server state, model choice, prompts, and cache warmth all affect the result.

## Reproduction protocol

1. Pin the agent, model, Serena version, and Semble version for the complete run.
2. Start each trial in a fresh conversation against the same repository revision and with equivalent warm or cold caches.
3. For the reference task, choose a project symbol whose name is also exported by a dependency. Ask for all real references and require file-and-line evidence.
4. Compare Serena's reference lookup with a built-in name-search workflow. Count every tool call and evaluate whether each reported location is a semantic reference rather than a same-name occurrence.
5. For the read-and-reason task, provide a known file and ask a question that requires following a small amount of nearby context. Compare Serena's symbolic route with built-in file reading and literal search.
6. Record raw transcripts, tool schemas, client versions, repository revision, cache state, call counts, elapsed time, token usage, and answer correctness.
7. Repeat each condition enough times to expose model and tool variance before publishing aggregate results.

The original private corpus is not included, so the exact historical counts cannot be independently reconstructed from this repository. The protocol above is the reproducible part; new public claims should include a redistributable fixture or repository revision and the raw transcripts.
