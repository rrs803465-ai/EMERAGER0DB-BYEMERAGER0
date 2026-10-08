"""Column data types, value coercion and comparison rules."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..errors import DataTypeError


class DataType(str, Enum):
    """Column types supported by Emerager0DB 0.1 beta. Add new members here to extend the type system."""

    INTEGER = "INTEGER"
    REAL = "REAL"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"


_ALIASES: dict[str, DataType] = {
    "INTEGER": DataType.INTEGER,
    "INT": DataType.INTEGER,
    "BIGINT": DataType.INTEGER,
    "REAL": DataType.REAL,
    "FLOAT": DataType.REAL,
    "DOUBLE": DataType.REAL,
    "TEXT": DataType.TEXT,
    "VARCHAR": DataType.TEXT,
    "STRING": DataType.TEXT,
    "CHAR": DataType.TEXT,
    "BOOLEAN": DataType.BOOLEAN,
    "BOOL": DataType.BOOLEAN,
}


def parse_type(name: str) -> DataType:
    """Map a type name written in SQL (case-insensitive, with common aliases) to a DataType."""
    try:
        return _ALIASES[name.upper()]
    except KeyError:
        raise DataTypeError(f"unknown data type '{name}'") from None


def describe(value: Any) -> str:
    """Human-readable type name of a Python value, used in error messages."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    return "TEXT"


def coerce(value: Any, dtype: DataType, column: str = "value") -> Any:
    """Validate value against dtype and return its canonical form. NULL (None) is always accepted."""
    if value is None:
        return None
    if dtype is DataType.INTEGER and isinstance(value, int) and not isinstance(value, bool):
        return value
    if dtype is DataType.REAL and isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if dtype is DataType.TEXT and isinstance(value, str):
        return value
    if dtype is DataType.BOOLEAN:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
    raise DataTypeError(f"column '{column}' expects {dtype.value}, got {describe(value)}")


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def compare_values(left: Any, right: Any) -> int:
    """Three-way comparison of two non-NULL values. Returns -1, 0 or 1.

    Numbers and booleans compare with each other. Text compares only with text.
    Any other pairing raises DataTypeError instead of silently ordering them.
    """
    kind_left, kind_right = _kind(left), _kind(right)
    if kind_left != kind_right and {kind_left, kind_right} != {"bool", "number"}:
        raise DataTypeError(f"cannot compare {describe(left)} with {describe(right)}")
    return (left > right) - (left < right)
