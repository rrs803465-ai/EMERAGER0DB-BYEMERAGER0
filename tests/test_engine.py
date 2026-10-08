import pytest

from emerager0db import connect
from emerager0db.errors import ConstraintError, CorruptDatabaseError, DataTypeError
from emerager0db.sql.dump import dump_sql


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "school.edb")
    conn.execute("CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);")
    return conn


def test_missing_values_become_null(db):
    db.execute("INSERT INTO students (id, name) VALUES (1, 'Rrs');")
    assert db.execute("SELECT * FROM students;").fetchall() == [(1, "Rrs", None)]


def test_update_rows_where_value_is_null(db):
    db.execute("INSERT INTO students (id, name) VALUES (1, 'Rrs');")
    result = db.execute("UPDATE students SET age = 13 WHERE age IS NULL;")
    assert result.rowcount == 1
    assert db.execute("SELECT age FROM students;").fetchall() == [(13,)]


def test_null_is_distinct_from_zero_and_empty_string(db):
    db.execute("INSERT INTO students VALUES (1, '', 0);")
    db.execute("INSERT INTO students (id) VALUES (2);")
    assert db.execute("SELECT id FROM students WHERE age = 0;").fetchall() == [(1,)]
    assert db.execute("SELECT id FROM students WHERE name IS NULL;").fetchall() == [(2,)]
    assert db.execute("SELECT id FROM students WHERE name IS NOT NULL;").fetchall() == [(1,)]


def test_where_order_by_and_limit(db):
    db.execute("INSERT INTO students VALUES (1, 'Ann', 15), (2, 'Bob', 13), (3, 'Cy', 13), (4, 'Dee', 17);")
    rows = db.execute("SELECT name FROM students WHERE age >= 13 ORDER BY age DESC, name LIMIT 2;").fetchall()
    assert rows == [("Dee",), ("Ann",)]


def test_distinct(db):
    db.execute("INSERT INTO students VALUES (1, 'a', 13), (2, 'b', 13), (3, 'c', 17);")
    assert db.execute("SELECT DISTINCT age FROM students ORDER BY age;").fetchall() == [(13,), (17,)]


def test_aggregates_ignore_nulls(db):
    db.execute("INSERT INTO students VALUES (1, 'A', 10), (2, 'B', 20);")
    db.execute("INSERT INTO students (id, name) VALUES (3, 'C');")
    row = db.execute(
        "SELECT COUNT(*), COUNT(age), SUM(age), AVG(age), MIN(age), MAX(age) FROM students;"
    ).fetchone()
    assert row == (3, 2, 30, 15.0, 10, 20)


def test_aggregate_over_empty_table_returns_one_row(db):
    assert db.execute("SELECT COUNT(*) FROM students;").fetchone() == (0,)


def test_group_by(db):
    db.execute("INSERT INTO students VALUES (1, 'A', 13), (2, 'B', 13), (3, 'C', 14);")
    rows = db.execute("SELECT age, COUNT(*) AS total FROM students GROUP BY age ORDER BY age;").fetchall()
    assert rows == [(13, 2), (14, 1)]


def test_not_null_and_primary_key_are_enforced(db):
    with pytest.raises(ConstraintError):
        db.execute("INSERT INTO students (name) VALUES ('no id');")
    db.execute("INSERT INTO students VALUES (1, 'a', 1);")
    with pytest.raises(ConstraintError, match="duplicate"):
        db.execute("INSERT INTO students VALUES (1, 'b', 2);")


def test_type_mismatch_is_rejected(db):
    with pytest.raises(DataTypeError):
        db.execute("INSERT INTO students VALUES (1, 42, 3);")


def test_failed_multi_row_insert_leaves_no_partial_rows(db):
    with pytest.raises(ConstraintError):
        db.execute("INSERT INTO students VALUES (1, 'a', 1), (1, 'b', 2);")
    assert db.execute("SELECT COUNT(*) FROM students;").fetchone() == (0,)


def test_alter_table_add_column_and_index_lookup(db):
    db.execute("INSERT INTO students VALUES (1, 'a', 2);")
    db.execute("ALTER TABLE students ADD COLUMN email TEXT;")
    assert db.execute("SELECT email FROM students;").fetchall() == [(None,)]
    db.execute("CREATE INDEX idx_name ON students (name);")
    assert db.execute("SELECT id FROM students WHERE name = 'a';").fetchall() == [(1,)]
    db.execute("UPDATE students SET name = 'z' WHERE id = 1;")
    assert db.execute("SELECT id FROM students WHERE name = 'a';").fetchall() == []
    assert db.execute("SELECT id FROM students WHERE name = 'z';").fetchall() == [(1,)]


def test_delete_with_where(db):
    db.execute("INSERT INTO students VALUES (1, 'a', 1), (2, 'b', 2);")
    assert db.execute("DELETE FROM students WHERE id = 1;").rowcount == 1
    assert db.execute("SELECT id FROM students;").fetchall() == [(2,)]


def test_persistence_across_reopen(tmp_path):
    path = tmp_path / "persist.edb"
    first = connect(path)
    first.execute("CREATE TABLE t (x INTEGER);")
    first.execute("INSERT INTO t VALUES (1), (2);")
    second = connect(path)
    assert second.execute("SELECT x FROM t ORDER BY x;").fetchall() == [(1,), (2,)]


def test_corrupted_file_is_detected(tmp_path):
    path = tmp_path / "corrupt.edb"
    conn = connect(path)
    conn.execute("CREATE TABLE t (x INTEGER);")
    data = bytearray(path.read_bytes())
    data[-5] ^= 0xFF
    path.write_bytes(bytes(data))
    with pytest.raises(CorruptDatabaseError):
        connect(path)


def test_non_database_file_is_rejected(tmp_path):
    path = tmp_path / "garbage.edb"
    path.write_bytes(b"this is not a database at all")
    with pytest.raises(CorruptDatabaseError):
        connect(path)


def test_transaction_rollback_and_commit(db):
    db.execute("BEGIN;")
    db.execute("INSERT INTO students VALUES (1, 'a', 1);")
    db.execute("ROLLBACK;")
    assert db.execute("SELECT COUNT(*) FROM students;").fetchone() == (0,)
    db.execute("BEGIN;")
    db.execute("INSERT INTO students VALUES (2, 'b', 2);")
    db.execute("COMMIT;")
    assert db.execute("SELECT COUNT(*) FROM students;").fetchone() == (1,)


def test_parameterized_api_treats_input_as_data(db):
    hostile = "Mallory'; DROP TABLE students; --"
    db.execute("INSERT INTO students VALUES (?, ?, ?);", (7, hostile, 20))
    assert db.execute("SELECT name FROM students WHERE id = ?;", (7,)).fetchall() == [(hostile,)]
    assert db.execute("SELECT COUNT(*) FROM students;").fetchone() == (1,)


def test_dump_and_restore_round_trip(db, tmp_path):
    db.execute("INSERT INTO students VALUES (1, 'O''Brien', 13), (2, NULL, NULL);")
    script = dump_sql(db.current)
    copy = connect(tmp_path / "copy.edb")
    copy.execute_script(script)
    original = db.execute("SELECT * FROM students ORDER BY id;").fetchall()
    assert copy.execute("SELECT * FROM students ORDER BY id;").fetchall() == original
