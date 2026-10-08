# CLI reference

## Command-line options

```text
Emerager0DB                     start the shell (runs first-run setup if no accounts exist)
Emerager0DB setup               create the root account (only when no accounts exist)
Emerager0DB update              install the latest verified release
Emerager0DB version             print the version
Emerager0DB --data-dir PATH     use a different data directory
Emerager0DB --debug             show internal tracebacks
```

## Dot-commands

Dot-commands start with a period and are not SQL.

| Command | What it does |
| --- | --- |
| `.help` | List the commands |
| `.tables` | List tables in the current database |
| `.databases` | List the databases you can read (current one marked with `*`) |
| `.schema <table>` | Show the `CREATE TABLE` statement for a table |
| `.describe <table>` | Show each column's type, nullability and key |
| `.use <database>` | Select a database (same as `USE`) |
| `.users` | List accounts and their roles |
| `.adduser` | Create an account (administrators only) |
| `.deluser <name>` | Delete an account (administrators only) |
| `.passwd` | Change your own password (asks for the current one) |
| `.status` | Show version, current database, tables, size, your role, and engine state |
| `.version` | Show the version |
| `.backup <path>` | Write a verified copy of the current database to `<path>` |
| `.export <path>` | Write the current database as an SQL script |
| `.import <path>` | Run an SQL script against the current database |
| `.clear` | Clear the screen |
| `.exit`, `.quit` | Leave the shell |

## Output

Result sets are aligned tables, and NULL is shown as `NULL`:

```text
id | name | age
---+------+-----
1  | Rrs  | NULL
(1 row)
```

Errors are one line starting with `Error:`. Example:

```text
rrs@Emerager0DB> SELECT * FROM does_not_exist;
Error: table 'does_not_exist' does not exist.
```

## Backups and exports

`.backup` copies the last committed state of the database file, after checking its checksum. It never reads or changes the live file in a way that could corrupt it. `.export` writes SQL you can replay with `.import` or `execute_script`.
