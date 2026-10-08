import pytest

from emerager0db.errors import Emerager0DBError, ParameterError, SQLSyntaxError
from emerager0db.sql import ast as A
from emerager0db.sql.lexer import statement_complete, tokenize
from emerager0db.sql.parser import Parser
from emerager0db.sql.tokens import TokenType


def test_lexer_handles_keywords_strings_operators_and_comments():
    tokens = tokenize("SELECT name FROM t WHERE x <> 'it''s' AND y >= 3.5 -- trailing\n")
    assert tokens[0].type is TokenType.KEYWORD and tokens[0].value == "SELECT"
    assert any(t.type is TokenType.STRING and t.value == "it's" for t in tokens)
    assert any(t.type is TokenType.OP and t.value == "!=" for t in tokens)
    assert any(t.type is TokenType.OP and t.value == ">=" for t in tokens)
    assert any(t.type is TokenType.REAL and t.value == 3.5 for t in tokens)


def test_lexer_reads_exponent_numbers():
    tokens = tokenize("1e3 2.5e-2")
    assert tokens[0].value == 1000.0
    assert tokens[1].value == 0.025


def test_unterminated_string_is_a_syntax_error():
    with pytest.raises(SQLSyntaxError, match="unterminated"):
        tokenize("SELECT 'abc")


def test_statement_complete_detects_semicolon_outside_strings():
    assert statement_complete("SELECT 1;")
    assert not statement_complete("SELECT 'a;")
    assert not statement_complete("SELECT 1")


def test_parse_create_table_constraints():
    stmt = Parser("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE);").parse()[0]
    assert isinstance(stmt, A.CreateTable)
    assert [c.name for c in stmt.columns] == ["id", "name", "email"]
    assert stmt.columns[0].primary_key
    assert stmt.columns[1].not_null
    assert stmt.columns[2].unique


def test_parse_select_with_all_clauses():
    sql = (
        "SELECT DISTINCT name, age AS years FROM users "
        "WHERE age >= 13 AND NOT name IS NULL ORDER BY age DESC LIMIT 5;"
    )
    stmt = Parser(sql).parse()[0]
    assert isinstance(stmt, A.Select)
    assert stmt.distinct
    assert stmt.limit == 5
    assert stmt.order_by[0].descending
    assert isinstance(stmt.where, A.BinaryOp) and stmt.where.op == "AND"
    assert stmt.items[1].alias == "years"


def test_parse_aggregates_and_group_by():
    stmt = Parser("SELECT COUNT(*), AVG(age) FROM users GROUP BY name;").parse()[0]
    assert isinstance(stmt.items[0].expr, A.Aggregate)
    assert stmt.items[0].expr.arg is None
    assert stmt.group_by == ("name",)


def test_placeholders_are_bound_as_values_not_text():
    stmt = Parser("INSERT INTO t VALUES (?, ?)", (1, "O'Brien; DROP TABLE t")).parse()[0]
    assert stmt.rows[0][1].value == "O'Brien; DROP TABLE t"


def test_placeholder_count_mismatch_is_rejected():
    with pytest.raises(ParameterError):
        Parser("SELECT * FROM t WHERE a = ?", ()).parse()
    with pytest.raises(ParameterError):
        Parser("SELECT * FROM t;", (1,)).parse()


@pytest.mark.parametrize(
    "sql",
    [
        "SELEC * FROM t",
        "SELECT FROM t",
        "CREATE TABLE t (",
        "INSERT INTO t VALUES 1",
        "SELECT * FROM t WHERE",
        "DROP DATABASE",
        "UPDATE t SET",
    ],
)
def test_malformed_sql_raises_friendly_error(sql):
    with pytest.raises(Emerager0DBError):
        Parser(sql).parse()
