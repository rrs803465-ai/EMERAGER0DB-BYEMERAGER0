"""Write a database as a replayable SQL script (CREATE TABLE, INSERT, CREATE INDEX)."""

from __future__ import annotations

import math
from typing import Any

from ..engine.database import Database
from ..engine.table import AUTO_INDEX_PREFIX, Table
from ..errors import Emerager0DBError
from ..version import __version__


def literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Emerager0DBError("non-finite REAL values cannot be exported")
        return repr(value)
    return "'" + value.replace("'", "''") + "'"


def create_table_sql(table: Table) -> str:
    parts: list[str] = []
    for column in table.columns:
        spec = f"{column.name} {column.dtype.value}"
        if column.primary_key:
            spec += " PRIMARY KEY"
        else:
            if column.not_null:
                spec += " NOT NULL"
            if column.unique:
                spec += " UNIQUE"
        parts.append(spec)
    body = ",\n    ".join(parts)
    return f"CREATE TABLE {table.name} (\n    {body}\n);"


def dump_sql(database: Database) -> str:
    lines = [f"-- Emerager0DB {__version__} dump of database '{database.name}'"]
    for table in database.tables.values():
        lines.append(create_table_sql(table))
        for rowid in sorted(table.rows):
            values = ", ".join(literal(value) for value in table.rows[rowid])
            lines.append(f"INSERT INTO {table.name} VALUES ({values});")
        for index in table.indexes.values():
            if index.name.startswith(AUTO_INDEX_PREFIX):
                continue
            kind = "UNIQUE INDEX" if index.unique else "INDEX"
            lines.append(f"CREATE {kind} {index.name} ON {table.name} ({index.column});")
    return "\n".join(lines) + "\n"
