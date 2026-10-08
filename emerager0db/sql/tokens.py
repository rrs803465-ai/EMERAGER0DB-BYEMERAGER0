"""Token definitions for the SQL lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class TokenType(Enum):
    KEYWORD = auto()
    IDENT = auto()
    INTEGER = auto()
    REAL = auto()
    STRING = auto()
    PARAM = auto()
    OP = auto()
    PUNCT = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: Any
    pos: int


KEYWORDS = frozenset(
    {
        "ADD", "ALTER", "AND", "AS", "ASC", "BEGIN", "BY", "COLUMN", "COMMIT", "CREATE", "DATABASE",
        "DELETE", "DESC", "DISTINCT", "DROP", "EXISTS", "FALSE", "FROM", "GRANT", "GROUP", "IF",
        "INDEX", "INSERT", "INTO", "IS", "KEY", "LIMIT", "NOT", "NULL", "ON", "OR", "ORDER", "PRIMARY",
        "REVOKE", "ROLLBACK", "SELECT", "SET", "TABLE", "TO", "TRANSACTION", "TRUE", "UNIQUE",
        "UPDATE", "USE", "VALUES", "WHERE",
    }
)
