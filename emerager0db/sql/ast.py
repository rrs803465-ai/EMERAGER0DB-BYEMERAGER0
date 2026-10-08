"""AST node definitions. Expressions and statements are immutable dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union


# ----- expressions -------------------------------------------------------

@dataclass(frozen=True)
class Literal:
    value: Any


@dataclass(frozen=True)
class ColumnRef:
    name: str


@dataclass(frozen=True)
class UnaryOp:
    op: str  # "NOT" or "-"
    operand: "Expr"


@dataclass(frozen=True)
class BinaryOp:
    op: str  # AND OR = != < <= > >=
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class IsNull:
    operand: "Expr"
    negated: bool


@dataclass(frozen=True)
class Aggregate:
    func: str  # COUNT SUM AVG MIN MAX
    arg: Optional[ColumnRef]  # None means COUNT(*)


Expr = Union[Literal, ColumnRef, UnaryOp, BinaryOp, IsNull, Aggregate]


# ----- supporting clauses ------------------------------------------------

@dataclass(frozen=True)
class ColumnDef:
    name: str
    type_name: str
    not_null: bool = False
    primary_key: bool = False
    unique: bool = False


@dataclass(frozen=True)
class SelectItem:
    expr: Expr
    alias: Optional[str]


@dataclass(frozen=True)
class OrderItem:
    column: str
    descending: bool


# ----- statements --------------------------------------------------------

@dataclass(frozen=True)
class CreateDatabase:
    name: str
    if_not_exists: bool = False


@dataclass(frozen=True)
class DropDatabase:
    name: str
    if_exists: bool = False


@dataclass(frozen=True)
class UseDatabase:
    name: str


@dataclass(frozen=True)
class CreateTable:
    name: str
    columns: tuple[ColumnDef, ...]
    if_not_exists: bool = False


@dataclass(frozen=True)
class DropTable:
    name: str
    if_exists: bool = False


@dataclass(frozen=True)
class AlterTableAddColumn:
    table: str
    column: ColumnDef


@dataclass(frozen=True)
class CreateIndex:
    name: str
    table: str
    column: str
    unique: bool = False


@dataclass(frozen=True)
class DropIndex:
    name: str
    table: str


@dataclass(frozen=True)
class Insert:
    table: str
    columns: Optional[tuple[str, ...]]
    rows: tuple[tuple[Expr, ...], ...]


@dataclass(frozen=True)
class Select:
    items: Optional[tuple[SelectItem, ...]]  # None means SELECT *
    table: str
    distinct: bool
    where: Optional[Expr]
    group_by: tuple[str, ...]
    order_by: tuple[OrderItem, ...]
    limit: Optional[int]


@dataclass(frozen=True)
class Update:
    table: str
    assignments: tuple[tuple[str, Expr], ...]
    where: Optional[Expr]


@dataclass(frozen=True)
class Delete:
    table: str
    where: Optional[Expr]


@dataclass(frozen=True)
class Begin:
    pass


@dataclass(frozen=True)
class Commit:
    pass


@dataclass(frozen=True)
class Rollback:
    pass


@dataclass(frozen=True)
class Grant:
    permission: str
    database: str
    user: str
    revoke: bool = False


Statement = Union[
    CreateDatabase, DropDatabase, UseDatabase, CreateTable, DropTable, AlterTableAddColumn,
    CreateIndex, DropIndex, Insert, Select, Update, Delete, Begin, Commit, Rollback, Grant,
]
