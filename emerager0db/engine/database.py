"""A single Emerager0DB database, persisted as one .edb file (or held in memory when path is None)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..errors import CorruptDatabaseError, Emerager0DBError, TableExistsError, TableNotFoundError
from . import storage
from .table import Column, Table


class Database:
    """Tables, per-database grants and the owner of one database.

    Table names are case-insensitive. Grants map a username to a set of database-level
    permission names such as DATABASE_READ or TABLE_CREATE.
    """

    def __init__(
        self,
        name: str,
        owner: str,
        *,
        path: Path | str | None = None,
        tables: dict[str, Table] | None = None,
        grants: dict[str, set[str]] | None = None,
        created_at: int | None = None,
    ) -> None:
        self.name = name
        self.owner = owner
        self.path = Path(path) if path is not None else None
        self.tables: dict[str, Table] = tables if tables is not None else {}
        self.grants: dict[str, set[str]] = {user: set(perms) for user, perms in (grants or {}).items()}
        self.created_at = int(created_at if created_at is not None else time.time())

    # ----- tables ---------------------------------------------------------

    def has_table(self, name: str) -> bool:
        return name.lower() in self.tables

    def table(self, name: str) -> Table:
        try:
            return self.tables[name.lower()]
        except KeyError:
            raise TableNotFoundError(f"table '{name}' does not exist") from None

    def create_table(self, name: str, columns: list[Column], owner: str) -> Table:
        if self.has_table(name):
            raise TableExistsError(f"table '{name}' already exists")
        lowered = [column.name.lower() for column in columns]
        if len(set(lowered)) != len(lowered):
            raise Emerager0DBError("duplicate column name in CREATE TABLE")
        table = Table(name, columns, owner)
        self.tables[name.lower()] = table
        return table

    def drop_table(self, name: str) -> Table:
        table = self.table(name)
        del self.tables[name.lower()]
        return table

    # ----- persistence ----------------------------------------------------

    def size_on_disk(self) -> int:
        return self.path.stat().st_size if self.path is not None and self.path.exists() else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "database",
            "name": self.name,
            "owner": self.owner,
            "created_at": self.created_at,
            "grants": {user: sorted(perms) for user, perms in sorted(self.grants.items())},
            "tables": [table.to_dict() for table in self.tables.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path | str | None = None) -> "Database":
        tables: dict[str, Table] = {}
        for table_data in data["tables"]:
            table = Table.from_dict(table_data)
            tables[table.name.lower()] = table
        return cls(
            data["name"],
            data["owner"],
            path=path,
            tables=tables,
            grants={user: set(perms) for user, perms in data.get("grants", {}).items()},
            created_at=data.get("created_at"),
        )

    def save(self) -> None:
        if self.path is not None:
            storage.write_database(self.path, self.to_dict())

    @classmethod
    def load(cls, path: Path | str) -> "Database":
        target = Path(path)
        payload = storage.read_database(target)
        if payload.get("kind") != "database":
            raise CorruptDatabaseError(f"'{target}' is not an Emerager0DB database")
        return cls.from_dict(payload, target)
