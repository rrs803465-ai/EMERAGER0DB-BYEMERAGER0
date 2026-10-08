# Emerager0DB

A lightweight SQL database engine written in Python. Version `0.1.0-beta`.

Emerager0DB is a from-scratch engine: its own lexer, parser, executor, storage format, accounts and permissions. It does not wrap `sqlite3` or any other database.

## Install

Linux and macOS:

```sh
curl -fsSL https://falks.cyou/get | sh
```

Windows (PowerShell):

```powershell
irm https://falks.cyou/get.ps1 | iex
```

The installer downloads the release for your platform, verifies its SHA-256 against the published checksum file, installs it, and runs the setup wizard that creates the root account. No Python is needed for the standalone builds.

Supported platforms: Windows x86_64, Linux x86_64, Linux ARM64, macOS x86_64, macOS ARM64.

## Quick start

```text
$ Emerager0DB
Username: rrs
Password:
rrs@Emerager0DB> CREATE DATABASE school;
Database created.
rrs@Emerager0DB> USE school;
Using database 'school'.
rrs@Emerager0DB> CREATE TABLE students (id INTEGER, name TEXT, age INTEGER);
Table created.
rrs@Emerager0DB> INSERT INTO students (id, name) VALUES (1, 'Rrs');
1 row(s) inserted.
rrs@Emerager0DB> SELECT * FROM students;
id | name | age
---+------+-----
1  | Rrs  | NULL
(1 row)
rrs@Emerager0DB> UPDATE students SET age = 13 WHERE age IS NULL;
1 row(s) updated.
```

## Python API

```python
from emerager0db import connect

db = connect("school.edb")
db.execute("CREATE TABLE users (id INTEGER, name TEXT)")
db.execute("INSERT INTO users VALUES (?, ?)", (1, "Rrs"))
rows = db.execute("SELECT * FROM users").fetchall()
```

Placeholders are bound as values. They never become part of the SQL text, so user input cannot change a statement's structure.

## SQL supported in 0.1 beta

`CREATE`/`DROP` DATABASE and TABLE (with `IF [NOT] EXISTS`), `USE`, `ALTER TABLE ... ADD COLUMN`, `CREATE [UNIQUE] INDEX` and `DROP INDEX`, `INSERT`, `SELECT` (with `DISTINCT`, `WHERE`, `GROUP BY`, `ORDER BY`, `LIMIT`, and `COUNT`/`SUM`/`AVG`/`MIN`/`MAX`), `UPDATE`, `DELETE`, `GRANT`/`REVOKE`, and `BEGIN`/`COMMIT`/`ROLLBACK`.

Types: `INTEGER`, `REAL`, `TEXT`, `BOOLEAN`, plus `NULL`. Constraints: `NOT NULL`, `PRIMARY KEY`, `UNIQUE`.

Not in 0.1 beta: joins, subqueries, arithmetic expressions, `BLOB`, and `ALTER` operations other than adding columns. See `docs/sql.md`.

## Architecture

```
emerager0db/
  cli.py            banner, setup wizard, login, REPL
  commands/         dot-commands, output formatting, status
  session.py        Connection: principal, current database, transactions, grants
  auth/             passwords (PBKDF2), accounts, permission model
  sql/              lexer, parser, AST, executor, dump writer
  engine/           types, indexes, tables, databases, catalog, storage format, transactions
  update.py         update check and verified self-update
web/                Railway service: website, release API, installer endpoints
installer/          install.sh and install.ps1
```

Storage: each database is one `.edb` file. It is a 46-byte header (magic, format version, length, SHA-256) followed by a JSON body. Writes are atomic, so a crash leaves the old file or the new file, never a mix.

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

Debug mode shows internal tracebacks: `Emerager0DB --debug`, or set `EMERAGER0DB_DEBUG=1`.

## Release

Tag a version (`git tag v0.1.0-beta && git push --tags`). The GitHub Actions workflow in `.github/workflows/release.yml` tests and builds the executable on each platform's native runner, merges `SHA256SUMS`, and publishes the release. Then update `web/api/releases.json` (see `docs/updating.md`). See `docs/development.md` for the full process.

## Deployment (Railway)

Railway hosts the website and release API only. It does not host or store databases.

1. Create a Railway project and add a service from this GitHub repository. Railway builds the `Dockerfile`.
2. Set the variable `EMERAGER0DB_REPO_URL` to your repository URL. The banner's "Star the repo" line and the website links read it. The Docker image already includes `installer/`, so no installer variable is needed.
3. Attach your domain, for example `falks.cyou`, in the service's Networking settings. Point the DNS record at the Railway target that Railway shows.
4. Check `https://falks.cyou/api/health` and `https://falks.cyou/api/version`.

Railway provides `PORT` automatically. The service has no database and no secrets.

## Contributing

See `CONTRIBUTING.md`.

## License

MIT. See `LICENSE`.
