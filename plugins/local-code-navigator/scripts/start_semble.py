# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "filelock==3.32.4",
#   "semble[mcp]==0.5.5",
# ]
# ///

"""Start Semble with cross-process serialization for on-disk index writes.

Why this override exists (issue #2, reviewed 2026-08-24, revisit by 2027-02-24):

Semble's index cache write is not atomic. `SembleIndex.save()` writes bm25_index,
semantic_index, chunks and metadata in place, sequentially, with no temp-and-rename
and no lock. `_IndexCache._build_index` then wraps the whole write in

    try: save_index_to_cache(...)
    except Exception: logger.warning("Failed to save index cache ...")

so any damage is swallowed and the search still returns results. Two coding-agent
sessions starting together on the same repository share a cache directory and can
interleave those writes; a reader can observe metadata that does not match the
chunks beside it. The failure is silent by construction, which is what makes it
worth guarding rather than waiting for a bug report.

Measured: `tests/concurrent_index.py` did not reproduce corruption at six concurrent
builders, because the write is fast relative to the build and the window is narrow.
That is a reason to keep this cheap guard, not a reason to drop it -- a narrow window
still opens, and nothing downstream would report it.

The cost of the guard is this subclass, pinned to a private API. That API already
moved once (0.5.2 named it `_build_and_cache_index`), so the pin above is
load-bearing and `tests/semble_api_contract.py` asserts the shape on every CI run.
Replace this with an upstream contract as soon as one exists.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout
from semble import mcp as semble_mcp
from semble.cache import resolve_cache_folder

logger = logging.getLogger("local-code-navigator")

# Long enough for a large repository's first index build, short enough that a stale
# lock does not look like a hang. On expiry the build proceeds unserialized, which is
# exactly stock Semble's behavior -- degraded, never blocked.
LOCK_TIMEOUT_SECONDS = 600


class LockedIndexCache(semble_mcp._IndexCache):
    """Prevent concurrent processes from publishing the same index together."""

    def _build_index(
        self,
        source: str,
        ref: str | None,
        model_path: str,
        cache_key: tuple[str, tuple[Any, ...]],
    ) -> Any:
        encoded_key = json.dumps(
            [cache_key[0], [item.value for item in cache_key[1]]],
            separators=(",", ":"),
        ).encode("utf-8")
        lock_name = hashlib.sha256(encoded_key).hexdigest() + ".lock"
        lock_dir = Path(resolve_cache_folder()) / ".locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / lock_name

        try:
            # Semble rechecks its cache inside the lock. A process waiting here can
            # therefore load the index written by the process that acquired it first.
            with FileLock(lock_path, timeout=LOCK_TIMEOUT_SECONDS):
                return super()._build_index(source, ref, model_path, cache_key)
        except Timeout:
            logger.warning(
                "Timed out after %ss waiting for the Semble index lock at %s. "
                "Another process is likely still building the index for %r. "
                "Continuing without serialization: the index will still be built, but "
                "a concurrent writer could overwrite the cached copy. If no other "
                "session is running, delete that lock file and retry.",
                LOCK_TIMEOUT_SECONDS,
                lock_path,
                source,
            )
            return super()._build_index(source, ref, model_path, cache_key)


def main() -> None:
    semble_mcp._IndexCache = LockedIndexCache
    asyncio.run(semble_mcp.serve())


if __name__ == "__main__":
    main()
