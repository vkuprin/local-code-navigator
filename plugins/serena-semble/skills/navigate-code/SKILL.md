---
name: navigate-code
description: Route code discovery between Semble, Serena, and built-ins. Use for exploration, reference checks, renames, architecture tracing, or semantic search.
---

# Navigate code with Semble and Serena

Use the narrowest route that matches the question.

## Routing

1. Use Semble `search` when the user describes behavior or architecture but does not know the symbol name. Pass `${CLAUDE_PROJECT_DIR}` as `repo`, default to `top_k=10`, and keep snippets compact. Refine a weak query up to two times.
2. Use Semble `find_related` when a known file location should lead to similar implementations.
3. Use Serena for symbol and relationship questions: `find_symbol`, `find_declaration`, `find_implementations`, `find_referencing_symbols`, `get_symbols_overview`, `rename_symbol`, `replace_symbol_body`, and `get_diagnostics_for_file`.
4. Use built-in Read, Grep, and Glob for literal text, file discovery, and read-and-reason work. The Serena `claude-code` context deliberately leaves those jobs with the client; they are not second-class fallbacks.
5. If Context7 is installed, use it for library API documentation rather than treating repository search as dependency documentation.

For architecture tracing, start with Semble to locate endpoints, then use Serena references to confirm the actual relationship. Never report a name grep as a reference check.

## Serena constraints

- Do not call `activate_project`. The plugin starts Serena with the current `${CLAUDE_PROJECT_DIR}`, and the `claude-code` context does not expose that tool.
- Serena locations are 0-based. Add 1 before citing a Serena line to the user. Do not apply this adjustment to Semble results.
- Verify arithmetic yourself. Better structured input does not guarantee that totals inferred from it are correct.
- Fewer calls are an efficiency win, not independent proof that the conclusion is correct.

## Measured trade-off

On the ambiguous `Text` symbol in `packages/ui-mobile`, Serena reference lookup took 2 tool calls versus 19 with grep. Both approaches reached the same substantive conclusion.

For read-and-reason work, Read plus Grep was cheaper and more accurate: 4 calls versus 6. Use Serena for symbols, references, and atomic refactors—not for every code question.
