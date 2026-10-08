# SQL reference (0.1 beta)

Keywords are case-insensitive. Identifiers start with a letter and contain letters, digits and underscores (up to 63 characters). Identifiers beginning with `__` are reserved. Strings use single quotes, and a quote inside a string is doubled: `'O''Brien'`. Comments start with `--`.

## Databases

```sql
CREATE DATABASE school;
CREATE DATABASE IF NOT EXISTS school;
USE school;
DROP DATABASE school;
DROP DATABASE IF EXISTS school;
```

## Types

| Type | Accepts | Notes |
| --- | --- | --- |
| `INTEGER` | whole numbers | aliases: `INT`, `BIGINT` |
| `REAL` | numbers | aliases: `FLOAT`, `DOUBLE` |
| `TEXT` | strings | aliases: `VARCHAR(n)`, `STRING`, `CHAR` (the size is ignored) |
| `BOOLEAN` | `TRUE`, `FALSE` | aliases: `BOOL`; 0 and 1 are accepted |

Any column can hold `NULL` unless it is `NOT NULL` or `PRIMARY KEY`.

## Tables

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    age INTEGER
);

CREATE TABLE IF NOT EXISTS users (id INTEGER);

ALTER TABLE users ADD COLUMN nickname TEXT;

DROP TABLE users;
DROP TABLE IF EXISTS users;
```

Rules:

- `PRIMARY KEY` implies `NOT NULL` and uniqueness. Only one primary key per table.
- `UNIQUE` columns allow many `NULL`s. Each non-NULL value must be unique.
- `ALTER TABLE ... ADD COLUMN` cannot add `NOT NULL`, `PRIMARY KEY` or `UNIQUE` columns, because existing rows would break the constraint.

## Indexes

```sql
CREATE INDEX idx_students_name ON students (name);
CREATE UNIQUE INDEX idx_users_email ON users (email);
DROP INDEX idx_students_name ON students;
```

An index speeds up `WHERE column = value`. It is kept up to date automatically. Primary-key and unique columns get an index automatically.

## INSERT

```sql
INSERT INTO students VALUES (1, 'Rrs', 13);
INSERT INTO students (id, name) VALUES (2, 'Alex');       -- age is NULL
INSERT INTO students VALUES (3, 'Mia', 14), (4, 'Ola', 15);
```

If any row in a multi-row `INSERT` fails, none of its rows are kept.

## SELECT

```sql
SELECT * FROM students;
SELECT id, name FROM students WHERE age >= 13;
SELECT DISTINCT age FROM students ORDER BY age;
SELECT name, age AS years FROM students ORDER BY age DESC, name LIMIT 10;
```

Operators: `=`, `!=` (also `<>`), `<`, `<=`, `>`, `>=`, `AND`, `OR`, `NOT`, `IS NULL`, `IS NOT NULL`, and parentheses.

ORDER BY puts NULLs first in ascending order.

### Aggregates and GROUP BY

```sql
SELECT COUNT(*) FROM students;
SELECT COUNT(age), SUM(age), AVG(age), MIN(age), MAX(age) FROM students;
SELECT age, COUNT(*) AS total FROM students GROUP BY age ORDER BY age;
```

Rules:

- Aggregates ignore NULL, except `COUNT(*)`, which counts rows.
- `SUM` and `AVG` need a numeric column.
- An aggregate over zero rows returns one row: `COUNT` gives 0, and the others give NULL.
- A selected plain column must appear in `GROUP BY`.

## UPDATE and DELETE

```sql
UPDATE students SET age = 13 WHERE age IS NULL;
UPDATE students SET name = 'Ola', age = 15 WHERE id = 4;
DELETE FROM students WHERE id = 2;
```

Arithmetic in expressions (for example `SET age = age + 1`) is not supported in 0.1 beta. Set the new value explicitly instead.

A statement without `WHERE` affects every row.

## NULL

NULL means "no value". It is not zero, not an empty string and not false.

- `NULL = NULL` is unknown, so `WHERE x = NULL` matches nothing. Use `WHERE x IS NULL`.
- Comparing NULL with anything gives unknown, and a `WHERE` clause keeps only rows that are true.

## Transactions

```sql
BEGIN;
INSERT INTO students VALUES (5, 'Kai', 16);
ROLLBACK;     -- or COMMIT;
```

Transactions snapshot the database when they start. They are for the current connection.

## Permissions

```sql
GRANT READ ON school TO alice;
GRANT WRITE ON school TO alice;
GRANT TABLE_CREATE ON school TO alice;
GRANT TABLE_DROP ON school TO alice;
REVOKE WRITE ON school FROM alice;
```

See `docs/users-and-permissions.md`.

## Parameters

Use `?` placeholders in the Python API, and pass the values as a tuple. They are bound as values, never pasted into the SQL text.

```python
db.execute("SELECT * FROM students WHERE name = ?", ("O'Brien",))
```
