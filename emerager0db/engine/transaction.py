"""Snapshot transactions. BEGIN captures the database state, ROLLBACK restores it, COMMIT persists it."""

from __future__ import annotations

import copy

from .database import Database


class Transaction:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._snapshot = copy.deepcopy((database.tables, database.grants))

    def rollback(self) -> None:
        self.database.tables, self.database.grants = self._snapshot
