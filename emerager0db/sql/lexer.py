"""Lexer: turns SQL text into tokens. Strings use '' for an embedded quote; -- starts a comment."""

from __future__ import annotations

from ..errors import SQLSyntaxError
from .tokens import KEYWORDS, Token, TokenType

_TWO_CHAR_OPS = {"<=", ">=", "!=", "<>"}
_ONE_CHAR_OPS = {"=", "<", ">", "-"}
_PUNCT = {"(", ")", ",", ";", ".", "*"}


def tokenize(sql: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch.isspace():
            i += 1
            continue
        if sql.startswith("--", i):
            newline = sql.find("\n", i)
            i = n if newline == -1 else newline + 1
            continue
        start = i
        if ch.isalpha() or ch == "_":
            while i < n and (sql[i].isalnum() or sql[i] == "_"):
                i += 1
            word = sql[start:i]
            upper = word.upper()
            if upper in KEYWORDS:
                tokens.append(Token(TokenType.KEYWORD, upper, start))
            else:
                tokens.append(Token(TokenType.IDENT, word, start))
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            is_real = False
            while i < n and sql[i].isdigit():
                i += 1
            if i < n and sql[i] == "." and i + 1 < n and sql[i + 1].isdigit():
                is_real = True
                i += 1
                while i < n and sql[i].isdigit():
                    i += 1
            if i < n and sql[i] in "eE":
                j = i + 1
                if j < n and sql[j] in "+-":
                    j += 1
                if j < n and sql[j].isdigit():
                    is_real = True
                    i = j
                    while i < n and sql[i].isdigit():
                        i += 1
            text = sql[start:i]
            if is_real:
                tokens.append(Token(TokenType.REAL, float(text), start))
            else:
                tokens.append(Token(TokenType.INTEGER, int(text), start))
            continue
        if ch == "'":
            i += 1
            parts: list[str] = []
            while True:
                if i >= n:
                    raise SQLSyntaxError(f"unterminated string literal starting at position {start}")
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        parts.append("'")
                        i += 2
                        continue
                    i += 1
                    break
                parts.append(sql[i])
                i += 1
            tokens.append(Token(TokenType.STRING, "".join(parts), start))
            continue
        if ch == '"':
            end = sql.find('"', i + 1)
            if end == -1:
                raise SQLSyntaxError(f"unterminated quoted identifier starting at position {start}")
            name = sql[i + 1:end]
            if not name:
                raise SQLSyntaxError("empty quoted identifier")
            tokens.append(Token(TokenType.IDENT, name, start))
            i = end + 1
            continue
        if ch == "?":
            tokens.append(Token(TokenType.PARAM, None, start))
            i += 1
            continue
        pair = sql[i:i + 2]
        if pair in _TWO_CHAR_OPS:
            value = "!=" if pair == "<>" else pair
            tokens.append(Token(TokenType.OP, value, start))
            i += 2
            continue
        if ch in _ONE_CHAR_OPS:
            tokens.append(Token(TokenType.OP, ch, start))
            i += 1
            continue
        if ch in _PUNCT:
            tokens.append(Token(TokenType.PUNCT, ch, start))
            i += 1
            continue
        raise SQLSyntaxError(f"unexpected character {ch!r} at position {start}")
    tokens.append(Token(TokenType.EOF, None, n))
    return tokens


def statement_complete(text: str) -> bool:
    """True when text ends with a ';' outside any string literal. Used by the interactive shell."""
    try:
        tokens = tokenize(text)
    except SQLSyntaxError as exc:
        return "unterminated" not in str(exc)
    meaningful = [token for token in tokens if token.type is not TokenType.EOF]
    return bool(meaningful) and meaningful[-1].type is TokenType.PUNCT and meaningful[-1].value == ";"
