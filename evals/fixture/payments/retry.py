"""Transient failure handling."""

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_backoff(operation: Callable[[], T], attempts: int = 5) -> T:
    """Run an operation again after progressively longer pauses when it raises."""
    delay = 0.1
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            time.sleep(delay)
            delay *= 2
    assert last_error is not None
    raise last_error
