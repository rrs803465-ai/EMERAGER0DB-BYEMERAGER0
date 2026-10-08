"""Dot-commands for the interactive shell (.tables, .use, .backup, .adduser, ...)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..engine.catalog import Catalog
from ..engine.storage import atomic_write
from ..errors import Emerager0DBError
from ..prompts import read_line, read_secret
from ..session import Connection
from ..sql.dump import create_table_sql, dump_sql
from ..version import __version__
from .format import format_result, render_table
from .system import status_lines

HELP_TEXT = """Dot-commands:
  .help                 show this help
  .tables               list tables in the current database
  .databases            list databases you can read
  .schema <table>       show the CREATE TABLE statement for a table
  .describe <table>     show the columns of a table
  .use <database>       select a database
  .users                list accounts
  .adduser              create an account (administrators only)
  .deluser <name>       delete an account (administrators only)
  .passwd               change your password
  .status               show engine status
  .version              show the version
  .backup <path>        write a verified copy of the current database
  .export <path>        write the current database as an SQL script
  .import <path>        run an SQL script against the current database
  .clear                clear the screen
  .exit, .quit          leave Emerager0DB

SQL statements end with a semicolon, for example: SELECT * FROM students;"""


class MetaCommands:
    def __init__(self, connection: Connection, catalog: Catalog) -> None:
        self.connection = connection
        self.catalog = catalog
        self._handlers: dict[str, Callable[[list[str]], bool | None]] = {
            "help": self._help,
            "tables": self._tables,
            "databases": self._databases,
            "schema": self._schema,
            "describe": self._describe,
            "use": self._use,
            "users": self._users,
            "adduser": self._adduser,
            "deluser": self._deluser,
            "passwd": self._passwd,
            "status": self._status,
            "version": self._version,
            "backup": self._backup,
            "export": self._export,
            "import": self._import,
            "clear": self._clear,
            "exit": self._exit,
            "quit": self._exit,
        }

    def dispatch(self, line: str) -> bool:
        """Run one dot-command. Returns False when the shell should exit."""
        parts = line[1:].split()
        if not parts:
            return True
        command, args = parts[0].lower(), parts[1:]
        handler = self._handlers.get(command)
        if handler is None:
            print(f"Unknown command '.{command}'. Type .help for a list.")
            return True
        try:
            return handler(args) is not False
        except Emerager0DBError as exc:
            print(f"Error: {exc}")
            return True

    # ----- helpers --------------------------------------------------------

    def _current_database(self):
        database = self.connection.current
        if database is None:
            raise Emerager0DBError("no database selected. Use .use <database> or USE <name>;")
        return database

    @staticmethod
    def _need_arg(args: list[str], usage: str) -> str:
        if len(args) != 1:
            raise Emerager0DBError(f"usage: {usage}")
        return args[0]

    # ----- commands -------------------------------------------------------

    def _help(self, args: list[str]) -> None:
        print(HELP_TEXT)

    def _tables(self, args: list[str]) -> None:
        database = self._current_database()
        if not database.tables:
            print("(no tables)")
            return
        for table in database.tables.values():
            print(table.name)

    def _databases(self, args: list[str]) -> None:
        names = self.connection.list_databases()
        if not names:
            print("(no databases)")
            return
        current = self.connection.current_database
        for name in names:
            print(f"{'*' if name == current else ' '} {name}")

    def _schema(self, args: list[str]) -> None:
        table = self._current_database().table(self._need_arg(args, ".schema <table>"))
        print(create_table_sql(table))

    def _describe(self, args: list[str]) -> None:
        table = self._current_database().table(self._need_arg(args, ".describe <table>"))
        rows = []
        for column in table.columns:
            key = "PRIMARY KEY" if column.primary_key else ("UNIQUE" if column.unique else "")
            rows.append((column.name, column.dtype.value, "NO" if column.not_null else "YES", key))
        print(render_table(["column", "type", "nullable", "key"], rows))

    def _use(self, args: list[str]) -> None:
        name = self._need_arg(args, ".use <database>")
        print(format_result(self.connection.execute(f"USE {name};")))

    def _users(self, args: list[str]) -> None:
        rows = [
            (user.name, "administrator" if user.is_admin else "user", "yes" if user.is_root else "no")
            for user in self.connection.list_users()
        ]
        print(render_table(["user", "role", "root"], rows))

    def _adduser(self, args: list[str]) -> None:
        name = read_line("New username: ").lower()
        password = read_secret("Password: ")
        confirm = read_secret("Confirm password: ")
        if password != confirm:
            raise Emerager0DBError("passwords do not match")
        admin = read_line("Make this account an administrator? [y/N] ").lower() in ("y", "yes")
        self.connection.create_user(name, password, admin=admin)
        print(f"User '{name}' created.")

    def _deluser(self, args: list[str]) -> None:
        name = self._need_arg(args, ".deluser <name>")
        self.connection.delete_user(name)
        print(f"User '{name.lower()}' deleted.")

    def _passwd(self, args: list[str]) -> None:
        current = read_secret("Current password: ")
        new_password = read_secret("New password: ")
        confirm = read_secret("Confirm new password: ")
        if new_password != confirm:
            raise Emerager0DBError("passwords do not match")
        self.connection.change_password(
            self.connection.principal.name, new_password, current_password=current
        )
        print("Password changed.")

    def _status(self, args: list[str]) -> None:
        for line in status_lines(self.connection):
            print(line)

    def _version(self, args: list[str]) -> None:
        print(f"Emerager0DB {__version__}")

    def _backup(self, args: list[str]) -> None:
        destination = Path(self._need_arg(args, ".backup <path>"))
        self.connection.backup(str(destination))
        print(f"Backup written to {destination}")

    def _export(self, args: list[str]) -> None:
        destination = Path(self._need_arg(args, ".export <path>"))
        atomic_write(destination, dump_sql(self._current_database()).encode("utf-8"))
        print(f"Exported to {destination}")

    def _import(self, args: list[str]) -> None:
        source = Path(self._need_arg(args, ".import <path>"))
        try:
            script = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise Emerager0DBError(f"cannot read '{source}': {exc}") from exc
        for result in self.connection.iter_script(script):
            text = format_result(result)
            if text:
                print(text)

    def _clear(self, args: list[str]) -> None:
        print("\033[2J\033[H", end="")

    def _exit(self, args: list[str]) -> bool:
        return False
