"""Executes table-level statements against one database, enforcing permissions.

Every mutating statement is atomic: if any row fails a constraint, the rows already changed by
that statement are reverted before the error is raised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..auth import permissions as perm
from ..auth.permissions import Principal
from ..engine.database import Database
from ..engine.table import Column, Table
from ..engine.types import DataType, coerce, compare_values, parse_type
from ..errors import (
    ConstraintError,
    DataTypeError,
    Emerager0DBError,
    PermissionDeniedError,
    SQLSyntaxError,
    TableNotFoundError,
)
from . import ast as A


@dataclass
class Result:
    """Outcome of one statement: a row set for queries, or a status message for everything else."""

    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    rowcount: int = 0
    message: str | None = None
    mutated: bool = False

    def fetchall(self) -> list[tuple]:
        return list(self.rows)

    def fetchone(self) -> tuple | None:
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


# ----- expression evaluation -----------------------------------------------

_COMPARATORS: dict[str, Callable[[int], bool]] = {
    "=": lambda c: c == 0,
    "!=": lambda c: c != 0,
    "<": lambda c: c < 0,
    "<=": lambda c: c <= 0,
    ">": lambda c: c > 0,
    ">=": lambda c: c >= 0,
}


def _as_logic(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _binary(expr: A.BinaryOp, table: Table | None, row: list[Any] | None) -> Any:
    if expr.op in ("AND", "OR"):
        left = _as_logic(evaluate(expr.left, table, row))
        right = _as_logic(evaluate(expr.right, table, row))
        if expr.op == "AND":
            if left is False or right is False:
                return False
            if left is None or right is None:
                return None
            return True
        if left is True or right is True:
            return True
        if left is None or right is None:
            return None
        return False
    left = evaluate(expr.left, table, row)
    right = evaluate(expr.right, table, row)
    if left is None or right is None:
        return None  # Any comparison with NULL is unknown.
    return _COMPARATORS[expr.op](compare_values(left, right))


def evaluate(expr: A.Expr, table: Table | None, row: list[Any] | None) -> Any:
    """Evaluate expr against a row. Uses SQL three-valued logic: NULL propagates through comparisons."""
    if isinstance(expr, A.Literal):
        return expr.value
    if isinstance(expr, A.ColumnRef):
        if table is None or row is None:
            raise SQLSyntaxError(f"column '{expr.name}' cannot be used in this context")
        return row[table.column_position(expr.name)]
    if isinstance(expr, A.IsNull):
        return (evaluate(expr.operand, table, row) is None) != expr.negated
    if isinstance(expr, A.UnaryOp):
        value = evaluate(expr.operand, table, row)
        if expr.op == "NOT":
            return None if value is None else not bool(value)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DataTypeError("unary minus requires a numeric value")
        return -value
    if isinstance(expr, A.BinaryOp):
        return _binary(expr, table, row)
    raise SQLSyntaxError("aggregate functions are only allowed in the SELECT list")


def _conjuncts(expr: A.Expr) -> list[A.Expr]:
    if isinstance(expr, A.BinaryOp) and expr.op == "AND":
        return _conjuncts(expr.left) + _conjuncts(expr.right)
    return [expr]


def _column_literal(expr: A.Expr) -> tuple[str, Any] | None:
    """Return (column, value) for an equality between a column and a literal, otherwise None."""
    if not isinstance(expr, A.BinaryOp) or expr.op != "=":
        return None
    if isinstance(expr.left, A.ColumnRef) and isinstance(expr.right, A.Literal):
        return expr.left.name, expr.right.value
    if isinstance(expr.right, A.ColumnRef) and isinstance(expr.left, A.Literal):
        return expr.right.name, expr.left.value
    return None


def _sort_key(value: Any) -> tuple[bool, Any]:
    """NULLs sort first in ascending order."""
    return (value is not None, value if value is not None else 0)


def _column_from_def(definition: A.ColumnDef) -> Column:
    return Column(
        name=definition.name,
        dtype=parse_type(definition.type_name),
        not_null=definition.not_null,
        primary_key=definition.primary_key,
        unique=definition.unique,
    )


def _expr_name(expr: A.Expr) -> str:
    return expr.name if isinstance(expr, A.ColumnRef) else "expression"


def _aggregate_name(agg: A.Aggregate) -> str:
    argument = agg.arg.name if agg.arg is not None else "*"
    return f"{agg.func}({argument})"


def _aggregate(agg: A.Aggregate, table: Table, members: list[list[Any]]) -> Any:
    if agg.arg is None:
        return len(members)
    position = table.column_position(agg.arg.name)
    values = [row[position] for row in members if row[position] is not None]
    if agg.func == "COUNT":
        return len(values)
    if not values:
        return None
    if agg.func in ("SUM", "AVG"):
        dtype = table.columns[position].dtype
        if dtype not in (DataType.INTEGER, DataType.REAL):
            raise DataTypeError(f"{agg.func} requires a numeric column, '{agg.arg.name}' is {dtype.value}")
        total = sum(values)
        return total if agg.func == "SUM" else total / len(values)
    if agg.func == "MIN":
        return min(values)
    if agg.func == "MAX":
        return max(values)
    raise SQLSyntaxError(f"unknown function {agg.func}")


# ----- executor -------------------------------------------------------------

class Executor:
    def __init__(
        self,
        database: Database,
        principal: Principal,
        admin_names: frozenset[str] = frozenset(),
    ) -> None:
        self.db = database
        self.principal = principal
        self.admin_names = admin_names

    def run(self, statement: A.Statement) -> Result:
        if isinstance(statement, A.CreateTable):
            return self._create_table(statement)
        if isinstance(statement, A.DropTable):
            return self._drop_table(statement)
        if isinstance(statement, A.AlterTableAddColumn):
            return self._alter_add_column(statement)
        if isinstance(statement, A.CreateIndex):
            return self._create_index(statement)
        if isinstance(statement, A.DropIndex):
            return self._drop_index(statement)
        if isinstance(statement, A.Insert):
            return self._insert(statement)
        if isinstance(statement, A.Select):
            return self._select(statement)
        if isinstance(statement, A.Update):
            return self._update(statement)
        if isinstance(statement, A.Delete):
            return self._delete(statement)
        raise Emerager0DBError("this statement must be run by a connection")

    # ----- permission helpers ---------------------------------------------

    @staticmethod
    def _require(allowed: bool, action: str) -> None:
        if not allowed:
            raise PermissionDeniedError(f"permission denied: {action}")

    def _readable(self) -> None:
        self._require(perm.can_read_database(self.principal, self.db), f"read database '{self.db.name}'")

    def _writable(self) -> None:
        self._require(perm.can_write_database(self.principal, self.db), f"write to database '{self.db.name}'")

    def _schema_change(self, table_name: str) -> Table:
        self._require(
            perm.can_create_table(self.principal, self.db),
            f"change table '{table_name}' in database '{self.db.name}'",
        )
        return self.db.table(table_name)

    # ----- DDL ------------------------------------------------------------

    def _create_table(self, s: A.CreateTable) -> Result:
        self._require(perm.can_create_table(self.principal, self.db), f"create tables in '{self.db.name}'")
        if self.db.has_table(s.name) and s.if_not_exists:
            return Result(message=f"Table '{s.name}' already exists.")
        columns = [_column_from_def(definition) for definition in s.columns]
        self.db.create_table(s.name, columns, owner=self.principal.name)
        return Result(message="Table created.", mutated=True)

    def _drop_table(self, s: A.DropTable) -> Result:
        if not self.db.has_table(s.name) and s.if_exists:
            return Result(message=f"Table '{s.name}' does not exist.")
        table = self.db.table(s.name)
        self._require(
            perm.can_drop_table(self.principal, self.db, table, self.admin_names),
            f"drop table '{table.name}'",
        )
        self.db.drop_table(s.name)
        return Result(message=f"Table '{table.name}' dropped.", mutated=True)

    def _alter_add_column(self, s: A.AlterTableAddColumn) -> Result:
        table = self._schema_change(s.table)
        table.add_column(_column_from_def(s.column))
        return Result(message=f"Column '{s.column.name}' added to '{table.name}'.", mutated=True)

    def _create_index(self, s: A.CreateIndex) -> Result:
        table = self._schema_change(s.table)
        table.create_index(s.name, s.column, s.unique)
        return Result(message=f"Index '{s.name}' created.", mutated=True)

    def _drop_index(self, s: A.DropIndex) -> Result:
        table = self._schema_change(s.table)
        table.drop_index(s.name)
        return Result(message=f"Index '{s.name}' dropped.", mutated=True)

    # ----- DML ------------------------------------------------------------

    def _insert(self, s: A.Insert) -> Result:
        self._writable()
        table = self.db.table(s.table)
        if s.columns is None:
            positions = list(range(len(table.columns)))
        else:
            lowered = [name.lower() for name in s.columns]
            if len(set(lowered)) != len(lowered):
                raise ConstraintError("a column is listed more than once in INSERT")
            positions = [table.column_position(name) for name in s.columns]
        inserted: list[int] = []
        try:
            for value_row in s.rows:
                if len(value_row) != len(positions):
                    raise ConstraintError(
                        f"INSERT provides {len(value_row)} values for {len(positions)} columns"
                    )
                values: list[Any] = [None] * len(table.columns)
                for position, expr in zip(positions, value_row):
                    values[position] = evaluate(expr, None, None)
                inserted.append(table.insert(values))
        except Exception:
            for rowid in reversed(inserted):
                table.delete_row(rowid)
            raise
        return Result(message=f"{len(inserted)} row(s) inserted.", rowcount=len(inserted), mutated=True)

    def _matching_rowids(self, table: Table, where: A.Expr | None) -> list[int]:
        candidates = self._candidate_rowids(table, where)
        if where is None:
            return candidates
        return [rowid for rowid in candidates if _truthy(evaluate(where, table, table.rows[rowid]))]

    def _candidate_rowids(self, table: Table, where: A.Expr | None) -> list[int]:
        """Use an index for the first indexed equality in the WHERE clause, otherwise scan all rows."""
        if where is not None:
            for conjunct in _conjuncts(where):
                pair = _column_literal(conjunct)
                if pair is None:
                    continue
                column, literal = pair
                index = table.index_for_column(column)
                if index is None:
                    continue
                dtype = table.column(column).dtype
                try:
                    key = coerce(literal, dtype, column)
                except DataTypeError:
                    continue  # Let row evaluation report the type mismatch.
                if key is None:
                    return []
                return sorted(index.lookup(key))
        return sorted(table.rows)

    def _update(self, s: A.Update) -> Result:
        self._writable()
        table = self.db.table(s.table)
        assignments = [(table.column_position(name), expr) for name, expr in s.assignments]
        targets = self._matching_rowids(table, s.where)
        changed: list[tuple[int, list[Any]]] = []
        try:
            for rowid in targets:
                old_row = table.rows[rowid]
                new_row = list(old_row)
                for position, expr in assignments:
                    new_row[position] = evaluate(expr, table, old_row)
                previous = table.replace_row(rowid, new_row)
                changed.append((rowid, previous))
        except Exception:
            for rowid, previous in reversed(changed):
                table.restore_row(rowid, previous)
            raise
        return Result(message=f"{len(changed)} row(s) updated.", rowcount=len(changed), mutated=True)

    def _delete(self, s: A.Delete) -> Result:
        self._writable()
        table = self.db.table(s.table)
        targets = self._matching_rowids(table, s.where)
        removed: list[tuple[int, list[Any]]] = []
        try:
            for rowid in targets:
                removed.append((rowid, table.delete_row(rowid)))
        except Exception:
            for rowid, row in reversed(removed):
                table.restore_row(rowid, row)
            raise
        return Result(message=f"{len(removed)} row(s) deleted.", rowcount=len(removed), mutated=True)

    # ----- SELECT ---------------------------------------------------------

    def _select(self, s: A.Select) -> Result:
        self._readable()
        table = self.db.table(s.table)
        has_aggregate = s.items is not None and any(isinstance(item.expr, A.Aggregate) for item in s.items)
        if has_aggregate or s.group_by:
            return self._grouped_select(table, s)
        rows = [table.rows[rowid] for rowid in self._matching_rowids(table, s.where)]
        if s.order_by:
            rows = self._sort_source_rows(table, rows, s.order_by)
        projection = self._projection(table, s.items)
        columns = [name for name, _ in projection]
        output = [tuple(evaluate(expr, table, row) for _, expr in projection) for row in rows]
        return self._finish(output, columns, s)

    @staticmethod
    def _projection(table: Table, items: tuple[A.SelectItem, ...] | None) -> list[tuple[str, A.Expr]]:
        if items is None:
            return [(column.name, A.ColumnRef(column.name)) for column in table.columns]
        return [(item.alias or _expr_name(item.expr), item.expr) for item in items]

    @staticmethod
    def _sort_source_rows(table: Table, rows: list[list[Any]], order: tuple[A.OrderItem, ...]) -> list[list[Any]]:
        # Stable sorts applied from the least significant key to the most significant one.
        for item in reversed(order):
            position = table.column_position(item.column)
            rows.sort(key=lambda row, p=position: _sort_key(row[p]), reverse=item.descending)
        return rows

    def _grouped_select(self, table: Table, s: A.Select) -> Result:
        if s.items is None:
            raise SQLSyntaxError("SELECT * cannot be combined with aggregate functions or GROUP BY")
        group_positions = [table.column_position(name) for name in s.group_by]
        key_index = {position: i for i, position in enumerate(group_positions)}
        rows = [table.rows[rowid] for rowid in self._matching_rowids(table, s.where)]
        groups: dict[tuple, list[list[Any]]] = {}
        for row in rows:
            key = tuple(row[position] for position in group_positions)
            groups.setdefault(key, []).append(row)
        if not group_positions and not groups:
            groups[()] = []  # An aggregate over no rows still yields one row.

        columns: list[str] = []
        plain_positions: list[int | None] = []
        for item in s.items:
            if isinstance(item.expr, A.Aggregate):
                columns.append(item.alias or _aggregate_name(item.expr))
                plain_positions.append(None)
            elif isinstance(item.expr, A.ColumnRef):
                position = table.column_position(item.expr.name)
                if position not in key_index:
                    raise SQLSyntaxError(
                        f"column '{item.expr.name}' must appear in GROUP BY or inside an aggregate function"
                    )
                columns.append(item.alias or table.columns[position].name)
                plain_positions.append(position)
            else:
                raise SQLSyntaxError("only columns and aggregate functions can be selected with GROUP BY")

        output: list[tuple] = []
        for key, members in groups.items():
            values: list[Any] = []
            for item, position in zip(s.items, plain_positions):
                if position is None:
                    values.append(_aggregate(item.expr, table, members))  # type: ignore[arg-type]
                else:
                    values.append(key[key_index[position]])
            output.append(tuple(values))
        if s.order_by:
            output = self._sort_output(output, columns, s.order_by)
        return self._finish(output, columns, s)

    @staticmethod
    def _sort_output(rows: list[tuple], columns: list[str], order: tuple[A.OrderItem, ...]) -> list[tuple]:
        lookup = {name.lower(): i for i, name in enumerate(columns)}
        for item in reversed(order):
            index = lookup.get(item.column.lower())
            if index is None:
                raise SQLSyntaxError(f"ORDER BY column '{item.column}' must be one of the selected columns")
            rows.sort(key=lambda row, i=index: _sort_key(row[i]), reverse=item.descending)
        return rows

    @staticmethod
    def _finish(rows: list[tuple], columns: list[str], s: A.Select) -> Result:
        if s.distinct:
            rows = list(dict.fromkeys(rows))
        if s.limit is not None:
            rows = rows[: s.limit]
        return Result(columns=columns, rows=rows, rowcount=len(rows))


def _truthy(value: Any) -> bool:
    return value is not None and bool(value)
