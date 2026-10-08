"""Table storage: column definitions, row storage, constraint checks and index maintenance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from ..errors import ColumnNotFoundError, ConstraintError, IndexExistsError, IndexNotFoundError
from .index import HashIndex
from .types import DataType, coerce

AUTO_INDEX_PREFIX = "__auto_"


@dataclass
class Column:
    """Definition of one column. PRIMARY KEY columns are always NOT NULL."""

    name: str
    dtype: DataType
    not_null: bool = False
    primary_key: bool = False
    unique: bool = False

    def __post_init__(self) -> None:
        if self.primary_key:
            self.not_null = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.dtype.value,
            "not_null": self.not_null,
            "primary_key": self.primary_key,
            "unique": self.unique,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Column":
        return cls(
            name=data["name"],
            dtype=DataType(data["type"]),
            not_null=data["not_null"],
            primary_key=data["primary_key"],
            unique=data["unique"],
        )


class Table:
    """A named collection of rows keyed by a monotonically increasing row id."""

    def __init__(
        self,
        name: str,
        columns: Iterable[Column],
        owner: str,
        *,
        rows: dict[int, list[Any]] | None = None,
        next_rowid: int | None = None,
        index_defs: list[dict[str, Any]] | None = None,
    ) -> None:
        self.columns: list[Column] = list(columns)
        if not self.columns:
            raise ConstraintError("a table needs at least one column")
        if sum(column.primary_key for column in self.columns) > 1:
            raise ConstraintError("a table can have only one PRIMARY KEY")
        self.name = name
        self.owner = owner
        self._positions = {column.name.lower(): i for i, column in enumerate(self.columns)}
        self.rows: dict[int, list[Any]] = dict(rows or {})
        self._next_rowid = next_rowid if next_rowid is not None else max(self.rows, default=0) + 1
        self.indexes: dict[str, HashIndex] = {}
        if index_defs is None:
            index_defs = [
                {"name": f"{AUTO_INDEX_PREFIX}{column.name.lower()}", "column": column.name, "unique": True}
                for column in self.columns
                if column.primary_key or column.unique
            ]
        for definition in index_defs:
            index = HashIndex(definition["name"], self.column(definition["column"]).name, definition["unique"])
            self.indexes[definition["name"].lower()] = index
        for rowid, row in self.rows.items():
            self._index_row(rowid, row)

    # ----- schema helpers -------------------------------------------------

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns]

    def column_position(self, name: str) -> int:
        try:
            return self._positions[name.lower()]
        except KeyError:
            raise ColumnNotFoundError(f"column '{name}' does not exist in table '{self.name}'") from None

    def column(self, name: str) -> Column:
        return self.columns[self.column_position(name)]

    def index_for_column(self, column_name: str) -> HashIndex | None:
        key = column_name.lower()
        for index in self.indexes.values():
            if index.column.lower() == key:
                return index
        return None

    def add_column(self, column: Column) -> None:
        """Append a nullable column. NOT NULL, PRIMARY KEY and UNIQUE are refused because existing rows would violate them."""
        if column.name.lower() in self._positions:
            raise ConstraintError(f"column '{column.name}' already exists in table '{self.name}'")
        if column.not_null or column.primary_key or column.unique:
            raise ConstraintError("ALTER TABLE ... ADD COLUMN cannot add NOT NULL, PRIMARY KEY or UNIQUE columns")
        self.columns.append(column)
        self._positions[column.name.lower()] = len(self.columns) - 1
        for row in self.rows.values():
            row.append(None)

    def create_index(self, name: str, column_name: str, unique: bool = False) -> None:
        key = name.lower()
        if key in self.indexes:
            raise IndexExistsError(f"index '{name}' already exists on table '{self.name}'")
        position = self.column_position(column_name)
        index = HashIndex(name, self.columns[position].name, unique)
        for rowid in sorted(self.rows):
            value = self.rows[rowid][position]
            if unique and index.conflicts(value):
                raise ConstraintError(f"cannot create unique index '{name}': duplicate value {value!r}")
            index.add(value, rowid)
        self.indexes[key] = index

    def drop_index(self, name: str) -> None:
        key = name.lower()
        if key not in self.indexes or key.startswith(AUTO_INDEX_PREFIX):
            raise IndexNotFoundError(f"index '{name}' does not exist on table '{self.name}'")
        del self.indexes[key]

    # ----- row operations -------------------------------------------------

    def insert(self, values: list[Any]) -> int:
        """Validate and store a full row (one value per column). Returns the new row id."""
        row = self._validate_row(values)
        rowid = self._next_rowid
        self._next_rowid += 1
        self.rows[rowid] = row
        self._index_row(rowid, row)
        return rowid

    def replace_row(self, rowid: int, values: list[Any]) -> list[Any]:
        """Validate and replace a stored row. Returns the previous row so the caller can roll back."""
        old = self.rows[rowid]
        new = self._validate_row(values, rowid=rowid)
        self._unindex_row(rowid, old)
        self.rows[rowid] = new
        self._index_row(rowid, new)
        return old

    def delete_row(self, rowid: int) -> list[Any]:
        old = self.rows.pop(rowid)
        self._unindex_row(rowid, old)
        return old

    def restore_row(self, rowid: int, row: list[Any]) -> None:
        """Put a row back exactly as it was. Used for statement and transaction rollback; skips validation."""
        if rowid in self.rows:
            self._unindex_row(rowid, self.rows[rowid])
        self.rows[rowid] = row
        self._index_row(rowid, row)

    def iter_rows(self) -> Iterator[tuple[int, list[Any]]]:
        for rowid in sorted(self.rows):
            yield rowid, self.rows[rowid]

    # ----- internals ------------------------------------------------------

    def _validate_row(self, values: list[Any], rowid: int | None = None) -> list[Any]:
        if len(values) != len(self.columns):
            raise ConstraintError(f"row has {len(values)} values but table '{self.name}' has {len(self.columns)} columns")
        checked: list[Any] = []
        for column, value in zip(self.columns, values):
            converted = coerce(value, column.dtype, column.name)
            if converted is None and column.not_null:
                raise ConstraintError(f"NULL value in column '{column.name}' violates NOT NULL constraint")
            checked.append(converted)
        for index in self.indexes.values():
            if index.unique:
                value = checked[self.column_position(index.column)]
                if index.conflicts(value, rowid):
                    raise ConstraintError(f"duplicate value for unique column '{index.column}': {value!r}")
        return checked

    def _index_row(self, rowid: int, row: list[Any]) -> None:
        for index in self.indexes.values():
            index.add(row[self.column_position(index.column)], rowid)

    def _unindex_row(self, rowid: int, row: list[Any]) -> None:
        for index in self.indexes.values():
            index.remove(row[self.column_position(index.column)], rowid)

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "owner": self.owner,
            "columns": [column.to_dict() for column in self.columns],
            "next_rowid": self._next_rowid,
            "indexes": [
                {"name": index.name, "column": index.column, "unique": index.unique}
                for index in self.indexes.values()
            ],
            "rows": [[rowid, row] for rowid, row in self.iter_rows()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Table":
        columns = [Column.from_dict(item) for item in data["columns"]]
        rows = {int(rowid): list(row) for rowid, row in data["rows"]}
        return cls(
            data["name"],
            columns,
            data["owner"],
            rows=rows,
            next_rowid=data["next_rowid"],
            index_defs=data["indexes"],
        )
