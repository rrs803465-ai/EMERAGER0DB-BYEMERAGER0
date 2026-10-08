"""Recursive-descent parser: token stream to AST.

Placeholders (?) are bound as values while parsing. They never become part of the SQL text,
so user input cannot change the structure of a statement.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..engine.types import parse_type
from ..errors import ParameterError, SQLSyntaxError
from ..names import validate_identifier
from . import ast as A
from .lexer import tokenize
from .tokens import Token, TokenType

AGGREGATES = frozenset({"COUNT", "SUM", "AVG", "MIN", "MAX"})
_COMPARISON_OPS = frozenset({"=", "!=", "<", "<=", ">", ">="})


class Parser:
    def __init__(self, sql: str, params: Sequence[Any] = ()) -> None:
        self._sql = sql
        self._tokens = tokenize(sql)
        self._pos = 0
        self._params = list(params)
        self._next_param = 0

    # ----- entry point ----------------------------------------------------

    def parse(self) -> list[A.Statement]:
        statements: list[A.Statement] = []
        while True:
            while self._match_symbol(";"):
                pass
            if self._peek().type is TokenType.EOF:
                break
            statements.append(self._statement())
            if self._peek().type is not TokenType.EOF and not self._match_symbol(";"):
                raise self._error("expected ';' after statement")
        if self._next_param != len(self._params):
            raise ParameterError(
                f"{len(self._params)} parameter(s) supplied but the SQL uses {self._next_param}"
            )
        return statements

    # ----- token helpers --------------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        return self._tokens[min(self._pos + offset, len(self._tokens) - 1)]

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        if token.type is not TokenType.EOF:
            self._pos += 1
        return token

    def _error(self, message: str) -> SQLSyntaxError:
        token = self._peek()
        if token.type is TokenType.EOF:
            near = "end of input"
        else:
            snippet = self._sql[token.pos:token.pos + 24].splitlines()[0]
            near = f"'{snippet}'"
        return SQLSyntaxError(f"{message} near {near}")

    def _match_keyword(self, *words: str) -> str | None:
        token = self._peek()
        if token.type is TokenType.KEYWORD and token.value in words:
            self._advance()
            return token.value
        return None

    def _expect_keyword(self, *words: str) -> str:
        value = self._match_keyword(*words)
        if value is None:
            raise self._error(f"expected {' or '.join(words)}")
        return value

    @staticmethod
    def _is_symbol(token: Token, symbol: str) -> bool:
        return token.type in (TokenType.PUNCT, TokenType.OP) and token.value == symbol

    def _match_symbol(self, symbol: str) -> bool:
        if self._is_symbol(self._peek(), symbol):
            self._advance()
            return True
        return False

    def _expect_symbol(self, symbol: str) -> None:
        if not self._match_symbol(symbol):
            raise self._error(f"expected '{symbol}'")

    def _identifier(self, what: str = "identifier") -> str:
        token = self._peek()
        if token.type is not TokenType.IDENT:
            raise self._error(f"expected {what}")
        self._advance()
        return token.value

    def _name(self, what: str) -> str:
        return validate_identifier(self._identifier(what), what)

    def _integer(self) -> int:
        token = self._peek()
        if token.type is not TokenType.INTEGER:
            raise self._error("expected an integer")
        self._advance()
        return token.value

    def _if_not_exists(self) -> bool:
        if self._match_keyword("IF"):
            self._expect_keyword("NOT")
            self._expect_keyword("EXISTS")
            return True
        return False

    def _if_exists(self) -> bool:
        if self._match_keyword("IF"):
            self._expect_keyword("EXISTS")
            return True
        return False

    # ----- statements -----------------------------------------------------

    def _statement(self) -> A.Statement:
        token = self._peek()
        if token.type is not TokenType.KEYWORD:
            raise self._error("expected a SQL statement")
        handlers = {
            "CREATE": self._create,
            "DROP": self._drop,
            "ALTER": self._alter,
            "USE": self._use,
            "INSERT": self._insert,
            "SELECT": self._select,
            "UPDATE": self._update,
            "DELETE": self._delete,
            "GRANT": lambda: self._grant(revoke=False),
            "REVOKE": lambda: self._grant(revoke=True),
            "BEGIN": self._begin,
            "COMMIT": self._commit,
            "ROLLBACK": self._rollback,
        }
        handler = handlers.get(token.value)
        if handler is None:
            raise self._error("unsupported statement")
        return handler()

    def _create(self) -> A.Statement:
        self._advance()
        unique = self._match_keyword("UNIQUE") is not None
        if self._match_keyword("INDEX"):
            return self._create_index(unique)
        if unique:
            raise self._error("expected INDEX after UNIQUE")
        kind = self._expect_keyword("DATABASE", "TABLE")
        if_not_exists = self._if_not_exists()
        name = self._name(f"{kind.lower()} name")
        if kind == "DATABASE":
            return A.CreateDatabase(name, if_not_exists)
        self._expect_symbol("(")
        columns = [self._column_def()]
        while self._match_symbol(","):
            columns.append(self._column_def())
        self._expect_symbol(")")
        return A.CreateTable(name, tuple(columns), if_not_exists)

    def _create_index(self, unique: bool) -> A.CreateIndex:
        name = self._name("index name")
        self._expect_keyword("ON")
        table = self._name("table name")
        self._expect_symbol("(")
        column = self._identifier("column name")
        self._expect_symbol(")")
        return A.CreateIndex(name, table, column, unique)

    def _column_def(self) -> A.ColumnDef:
        name = self._name("column name")
        type_token = self._peek()
        if type_token.type is not TokenType.IDENT:
            raise self._error("expected a data type")
        self._advance()
        type_name = type_token.value.upper()
        parse_type(type_name)  # Raises DataTypeError for unknown types.
        if self._match_symbol("("):
            self._integer()  # Size arguments such as VARCHAR(255) are accepted and ignored.
            self._expect_symbol(")")
        not_null = primary = unique = False
        while True:
            if self._match_keyword("NOT"):
                self._expect_keyword("NULL")
                not_null = True
            elif self._match_keyword("PRIMARY"):
                self._expect_keyword("KEY")
                primary = True
            elif self._match_keyword("UNIQUE"):
                unique = True
            elif self._match_keyword("NULL"):
                continue
            else:
                break
        return A.ColumnDef(name, type_name, not_null, primary, unique)

    def _drop(self) -> A.Statement:
        self._advance()
        kind = self._expect_keyword("DATABASE", "TABLE", "INDEX")
        if kind == "INDEX":
            name = self._name("index name")
            self._expect_keyword("ON")
            return A.DropIndex(name, self._name("table name"))
        if_exists = self._if_exists()
        name = self._name(f"{kind.lower()} name")
        if kind == "DATABASE":
            return A.DropDatabase(name, if_exists)
        return A.DropTable(name, if_exists)

    def _alter(self) -> A.AlterTableAddColumn:
        self._advance()
        self._expect_keyword("TABLE")
        table = self._name("table name")
        self._expect_keyword("ADD")
        self._match_keyword("COLUMN")
        return A.AlterTableAddColumn(table, self._column_def())

    def _use(self) -> A.UseDatabase:
        self._advance()
        return A.UseDatabase(self._name("database name"))

    def _insert(self) -> A.Insert:
        self._advance()
        self._expect_keyword("INTO")
        table = self._name("table name")
        columns: tuple[str, ...] | None = None
        if self._match_symbol("("):
            names = [self._identifier("column name")]
            while self._match_symbol(","):
                names.append(self._identifier("column name"))
            self._expect_symbol(")")
            columns = tuple(names)
        self._expect_keyword("VALUES")
        rows = [self._value_row()]
        while self._match_symbol(","):
            rows.append(self._value_row())
        return A.Insert(table, columns, tuple(rows))

    def _value_row(self) -> tuple[A.Expr, ...]:
        self._expect_symbol("(")
        values = [self._expr()]
        while self._match_symbol(","):
            values.append(self._expr())
        self._expect_symbol(")")
        return tuple(values)

    def _select(self) -> A.Select:
        self._advance()
        distinct = self._match_keyword("DISTINCT") is not None
        items: tuple[A.SelectItem, ...] | None
        if self._match_symbol("*"):
            items = None
        else:
            collected = [self._select_item()]
            while self._match_symbol(","):
                collected.append(self._select_item())
            items = tuple(collected)
        self._expect_keyword("FROM")
        table = self._name("table name")
        where = self._expr() if self._match_keyword("WHERE") else None
        group_by: tuple[str, ...] = ()
        if self._match_keyword("GROUP"):
            self._expect_keyword("BY")
            names = [self._identifier("column name")]
            while self._match_symbol(","):
                names.append(self._identifier("column name"))
            group_by = tuple(names)
        order_by: tuple[A.OrderItem, ...] = ()
        if self._match_keyword("ORDER"):
            self._expect_keyword("BY")
            orders = [self._order_item()]
            while self._match_symbol(","):
                orders.append(self._order_item())
            order_by = tuple(orders)
        limit = self._integer() if self._match_keyword("LIMIT") else None
        return A.Select(items, table, distinct, where, group_by, order_by, limit)

    def _select_item(self) -> A.SelectItem:
        token = self._peek()
        if (
            token.type is TokenType.IDENT
            and token.value.upper() in AGGREGATES
            and self._is_symbol(self._peek(1), "(")
        ):
            self._advance()
            self._advance()
            func = token.value.upper()
            if self._match_symbol("*"):
                if func != "COUNT":
                    raise self._error(f"{func}(*) is not supported")
                arg = None
            else:
                arg = A.ColumnRef(self._identifier("column name"))
            self._expect_symbol(")")
            expr: A.Expr = A.Aggregate(func, arg)
        else:
            expr = self._expr()
        alias = self._name("alias") if self._match_keyword("AS") else None
        return A.SelectItem(expr, alias)

    def _order_item(self) -> A.OrderItem:
        column = self._identifier("column name")
        descending = self._match_keyword("DESC") is not None
        self._match_keyword("ASC")
        return A.OrderItem(column, descending)

    def _update(self) -> A.Update:
        self._advance()
        table = self._name("table name")
        self._expect_keyword("SET")
        assignments = [self._assignment()]
        while self._match_symbol(","):
            assignments.append(self._assignment())
        where = self._expr() if self._match_keyword("WHERE") else None
        return A.Update(table, tuple(assignments), where)

    def _assignment(self) -> tuple[str, A.Expr]:
        column = self._identifier("column name")
        self._expect_symbol("=")
        return column, self._expr()

    def _delete(self) -> A.Delete:
        self._advance()
        self._expect_keyword("FROM")
        table = self._name("table name")
        where = self._expr() if self._match_keyword("WHERE") else None
        return A.Delete(table, where)

    def _grant(self, revoke: bool) -> A.Grant:
        self._advance()
        permission = self._identifier("permission name").upper()
        self._expect_keyword("ON")
        database = self._name("database name")
        self._expect_keyword("FROM" if revoke else "TO")
        user = self._identifier("user name").lower()
        return A.Grant(permission, database, user, revoke)

    def _begin(self) -> A.Begin:
        self._advance()
        self._match_keyword("TRANSACTION")
        return A.Begin()

    def _commit(self) -> A.Commit:
        self._advance()
        self._match_keyword("TRANSACTION")
        return A.Commit()

    def _rollback(self) -> A.Rollback:
        self._advance()
        self._match_keyword("TRANSACTION")
        return A.Rollback()

    # ----- expressions ----------------------------------------------------

    def _expr(self) -> A.Expr:
        left = self._and()
        while self._match_keyword("OR"):
            left = A.BinaryOp("OR", left, self._and())
        return left

    def _and(self) -> A.Expr:
        left = self._not()
        while self._match_keyword("AND"):
            left = A.BinaryOp("AND", left, self._not())
        return left

    def _not(self) -> A.Expr:
        if self._match_keyword("NOT"):
            return A.UnaryOp("NOT", self._not())
        return self._comparison()

    def _comparison(self) -> A.Expr:
        left = self._primary()
        if self._match_keyword("IS"):
            negated = self._match_keyword("NOT") is not None
            self._expect_keyword("NULL")
            return A.IsNull(left, negated)
        token = self._peek()
        if token.type is TokenType.OP and token.value in _COMPARISON_OPS:
            self._advance()
            return A.BinaryOp(token.value, left, self._primary())
        return left

    def _primary(self) -> A.Expr:
        token = self._peek()
        if token.type in (TokenType.INTEGER, TokenType.REAL, TokenType.STRING):
            self._advance()
            return A.Literal(token.value)
        if token.type is TokenType.PARAM:
            self._advance()
            return A.Literal(self._take_param())
        if token.type is TokenType.KEYWORD and token.value in ("TRUE", "FALSE", "NULL"):
            self._advance()
            return A.Literal({"TRUE": True, "FALSE": False, "NULL": None}[token.value])
        if token.type is TokenType.IDENT:
            self._advance()
            return A.ColumnRef(token.value)
        if self._is_symbol(token, "("):
            self._advance()
            inner = self._expr()
            self._expect_symbol(")")
            return inner
        if self._is_symbol(token, "-"):
            self._advance()
            number = self._peek()
            if number.type in (TokenType.INTEGER, TokenType.REAL):
                self._advance()
                return A.Literal(-number.value)
            raise self._error("expected a number after '-'")
        raise self._error("expected a value or column name")

    def _take_param(self) -> Any:
        if self._next_param >= len(self._params):
            raise ParameterError("more '?' placeholders in the SQL than parameters supplied")
        value = self._params[self._next_param]
        self._next_param += 1
        if value is not None and not isinstance(value, (bool, int, float, str)):
            raise ParameterError(f"unsupported parameter type: {type(value).__name__}")
        return value
