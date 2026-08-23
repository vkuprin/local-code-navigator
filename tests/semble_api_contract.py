# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "semble[mcp]==0.5.5",
# ]
# ///

"""Assert the private Semble API that scripts/start_semble.py overrides still exists.

The launcher subclasses `semble.mcp._IndexCache` and overrides `_build_index` to
serialize on-disk index writes across processes. That is a private API, and it has
already moved once: semble 0.5.2 named these `_build_and_cache_index` and
`_build_and_track`, and 0.5.5 renamed them to `_build_index` and `_build_tracked`.

A rename is invisible to a startup smoke test. Python resolves the base class at import
time, so the server still starts cleanly, and the override is only reached on the first
real `search` -- where it raises AttributeError, or silently stops locking. This check
fails loudly at the contract instead.

Keep the pin in this file's dependency block identical to the one in
plugins/local-code-navigator/scripts/start_semble.py.
"""

from __future__ import annotations

import inspect
import sys

EXPECTED_PARAMS = ["self", "source", "ref", "model_path", "cache_key"]

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f" -- {detail}"))
    if not ok:
        failures.append(label)


def main() -> int:
    from semble import mcp as semble_mcp

    print(f"semble.mcp: {semble_mcp.__file__}")

    cache_cls = getattr(semble_mcp, "_IndexCache", None)
    check("semble.mcp._IndexCache exists", cache_cls is not None,
          "the launcher's base class is gone; the override cannot apply")
    if cache_cls is None:
        return 1

    build = getattr(cache_cls, "_build_index", None)
    check("_IndexCache._build_index exists", build is not None,
          f"present members: {sorted(n for n in vars(cache_cls) if not n.startswith('__'))}")

    if build is not None:
        params = list(inspect.signature(build).parameters)
        check("_build_index signature unchanged", params == EXPECTED_PARAMS,
              f"expected {EXPECTED_PARAMS}, got {params}")

    try:
        from semble.cache import resolve_cache_folder
        folder = resolve_cache_folder()
        check("semble.cache.resolve_cache_folder is callable", bool(folder), f"returned {folder!r}")
    except Exception as exc:
        check("semble.cache.resolve_cache_folder is importable", False, f"{type(exc).__name__}: {exc}")

    # The launcher must import cleanly against this exact pin.
    try:
        import importlib.util
        from pathlib import Path
        launcher = Path(__file__).resolve().parent.parent / "plugins" / "local-code-navigator" / "scripts" / "start_semble.py"
        spec = importlib.util.spec_from_file_location("start_semble_under_test", launcher)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        check("start_semble.py imports against the pin", True)
        check("LockedIndexCache subclasses the current _IndexCache",
              issubclass(module.LockedIndexCache, cache_cls))
        check("LockedIndexCache._build_index actually overrides the base",
              module.LockedIndexCache._build_index is not cache_cls._build_index)
    except Exception as exc:
        check("start_semble.py imports against the pin", False, f"{type(exc).__name__}: {exc}")

    if failures:
        print("\nFAILED -- the pinned private Semble API changed shape.")
        print("Re-check scripts/start_semble.py against the installed semble version")
        print("before bumping the pin. See issue #2.")
        return 1
    print("\nprivate API contract intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
