# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "filelock==3.32.4",
#   "semble[mcp]==0.5.5",
# ]
# ///

"""Start Semble with cross-process serialization for on-disk index writes."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from filelock import FileLock
from semble import mcp as semble_mcp
from semble.cache import resolve_cache_folder


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

        # Semble rechecks its cache inside the lock. A process waiting here can
        # therefore load the index written by the process that acquired it first.
        with FileLock(lock_dir / lock_name, timeout=900):
            return super()._build_index(source, ref, model_path, cache_key)


def main() -> None:
    semble_mcp._IndexCache = LockedIndexCache
    asyncio.run(semble_mcp.serve())


if __name__ == "__main__":
    main()
