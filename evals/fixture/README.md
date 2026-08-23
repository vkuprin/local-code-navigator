# Routing fixture

A small synthetic codebase written for this repository, so the corpus is
redistributable and its ground truth is exact rather than inferred.

Each file exists to make one navigation question have a single defensible answer:

- `payments/gateway.py` defines `charge`, the symbol under test. `payments/legacy.py`
  defines an unrelated method also named `charge`, so a name-based text search returns
  a wrong answer and a real reference check returns a right one.
- `payments/retry.py` implements backoff without using the word "retry" in the body,
  so it is findable by behavior but not by grepping the obvious term.
- `notifications/` has one protocol and two implementations, for tracing implementations
  across files.
- `payments/ledger.py` is a single self-contained file, for reasoning that built-in
  file reading should answer without any symbolic tooling.
