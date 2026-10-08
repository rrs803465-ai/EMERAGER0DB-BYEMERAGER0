"""In-memory hash index. Indexes are rebuilt from rows when a database is loaded."""

from __future__ import annotations

from typing import Any


class HashIndex:
    """Maps column values to the set of row ids holding them. NULL values are never indexed."""

    __slots__ = ("name", "column", "unique", "_buckets")

    def __init__(self, name: str, column: str, unique: bool = False) -> None:
        self.name = name
        self.column = column
        self.unique = unique
        self._buckets: dict[Any, set[int]] = {}

    def add(self, value: Any, rowid: int) -> None:
        if value is not None:
            self._buckets.setdefault(value, set()).add(rowid)

    def remove(self, value: Any, rowid: int) -> None:
        if value is None:
            return
        bucket = self._buckets.get(value)
        if bucket is None:
            return
        bucket.discard(rowid)
        if not bucket:
            del self._buckets[value]

    def lookup(self, value: Any) -> set[int]:
        """Return a copy of the row ids whose indexed value equals value."""
        if value is None:
            return set()
        return set(self._buckets.get(value, ()))

    def conflicts(self, value: Any, rowid: int | None = None) -> bool:
        """True if value is already present on a row other than rowid (used for UNIQUE checks)."""
        if value is None:
            return False
        bucket = self._buckets.get(value)
        return bool(bucket) and any(existing != rowid for existing in bucket)
