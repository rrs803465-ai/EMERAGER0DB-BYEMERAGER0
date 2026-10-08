"""Command-line entry point: banner, first-run setup, login, the interactive shell and subcommands."""

from __future__ import annotations

import argparse
import threading
import traceback
from pathlib import Path

from . import config, update
from .auth.passwords import MIN_PASSWORD_LENGTH
from .auth.permissions import Permission
from .auth.users import UserStore, is_valid_username
from .commands.format import format_result
from .commands.meta import MetaCommands
from .engine.catalog import Catalog
from .errors import AuthenticationError, Emerager0DBError, UpdateError
from .prompts import read_line, read_secret
from .session import Connection
from .sql.lexer import statement_complete
from .version import __version__


def banner_lines() -> list[str]:
    return [
        "Emerager0DB",
        "All rights very very reserved.",
        "",
        "Version 0.1 beta",
        "Open-source project made by Emerager0",
        "(Original names: Rrs and Eyeups2)",
        "",
        "Hosted via Railway Cloudservice",
        "",
        "Star the repo if you like:",
        config.REPO_URL,
    ]


# ----- setup and login --------------------------------------------------------

def _prompt_username(prompt: str, users: UserStore) -> str:
    while True:
        name = read_line(prompt).lower()
        if not is_valid_username(name):
            print("Error: usernames use lowercase letters, digits, '_', '.' and '-', and start with a letter.")
        elif users.get(name) is not None:
            print(f"Error: user '{name}' already exists.")
        else:
            return name


def _prompt_new_password() -> str:
    while True:
        password = read_secret("Password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Error: password must be at least {MIN_PASSWORD_LENGTH} characters.")
            continue
        if read_secret("Confirm password: ") != password:
            print("Error: passwords do not match.")
            continue
        return password


def run_setup(users: UserStore) -> None:
    """First-run wizard: create the root administrator, then optionally create normal users."""
    print("Initial setup: create the root administrator account.")
    name = _prompt_username("Root username: ", users)
    password = _prompt_new_password()
    users.create(name, password, {Permission.ADMIN.value}, root=True)
    print(f"Root account '{name}' created.")
    while read_line("Create a normal user now? [y/N] ").lower() in ("y", "yes"):
        user_name = _prompt_username("Username: ", users)
        user_password = _prompt_new_password()
        users.create(user_name, user_password)
        print(f"User '{user_name}' created.")


def _login(catalog: Catalog, users: UserStore) -> Connection | None:
    for _ in range(3):
        name = read_line("Username: ")
        password = read_secret("Password: ")
        try:
            return Connection.login(catalog, users, name, password)
        except AuthenticationError as exc:
            print(f"Error: {exc}.")
    return None


def _start_update_check() -> tuple[threading.Thread | None, dict[str, str]]:
    result: dict[str, str] = {}
    if not config.UPDATE_CHECK_ENABLED:
        return None, result

    def worker() -> None:
        latest = update.check_for_update()
        if latest:
            result["latest"] = latest

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread, result


# ----- interactive shell ------------------------------------------------------

def run_sql(connection: Connection, sql: str, debug: bool) -> None:
    try:
        for result in connection.iter_script(sql):
            text = format_result(result)
            if text:
                print(text)
    except Emerager0DBError as exc:
        print(f"Error: {exc}")
    except Exception:  # Internal bugs must never show a raw traceback to normal users.
        if debug:
            traceback.print_exc()
        else:
            print("Error: an unexpected internal error occurred. Run with --debug for details.")


def repl(connection: Connection, catalog: Catalog, debug: bool) -> None:
    meta = MetaCommands(connection, catalog)
    buffer: list[str] = []
    while True:
        prompt = f"{connection.principal.name}@Emerager0DB> " if not buffer else "...> "
        try:
            line = input(prompt)
        except KeyboardInterrupt:
            print()
            buffer.clear()
            continue
        except EOFError:
            print()
            return
        stripped = line.strip()
        if not buffer and stripped.startswith("."):
            if not meta.dispatch(stripped):
                return
            continue
        if not buffer and not stripped:
            continue
        buffer.append(line)
        text = "\n".join(buffer)
        if statement_complete(text):
            buffer.clear()
            run_sql(connection, text, debug)


def _interactive(catalog: Catalog, users: UserStore, debug: bool) -> int:
    for line in banner_lines():
        print(line)
    print()
    if not users.has_users():
        print("No accounts found. Starting first-run setup.\n")
        run_setup(users)
        print()
    check_thread, check_result = _start_update_check()
    connection = _login(catalog, users)
    if connection is None:
        print("Error: too many failed login attempts.")
        return 1
    if check_thread is not None:
        check_thread.join(timeout=config.UPDATE_TIMEOUT_SECONDS)
    if check_result.get("latest"):
        print(f"A new Emerager0DB version is available: {check_result['latest']}")
        print("Run `Emerager0DB update` to update.")
        print()
    repl(connection, catalog, debug)
    return 0


def _run_update() -> int:
    try:
        installed = update.perform_update()
    except UpdateError as exc:
        print(f"Error: {exc}")
        return 1
    if installed is None:
        print(f"Emerager0DB {__version__} is already up to date.")
    else:
        print(f"Updated to {installed}. Restart Emerager0DB to use the new version.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="Emerager0DB", description="Emerager0DB SQL database shell.")
    parser.add_argument("--version", action="version", version=f"Emerager0DB {__version__}")
    parser.add_argument("--data-dir", type=Path, default=None, help="directory holding databases and accounts")
    parser.add_argument("--debug", action="store_true", help="show internal tracebacks")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("setup", help="create the root account (first run only)")
    subcommands.add_parser("update", help="install the latest release")
    subcommands.add_parser("version", help="print the version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    debug = args.debug or config.DEBUG
    if args.command == "version":
        print(f"Emerager0DB {__version__}")
        return 0
    if args.command == "update":
        return _run_update()
    root = args.data_dir or config.data_dir()
    catalog = Catalog(root)
    catalog.ensure_layout()
    users = UserStore(catalog.system_dir / "users.json")
    try:
        if args.command == "setup":
            if users.has_users():
                print("The root account already exists. Start Emerager0DB and log in to manage accounts.")
                return 0
            run_setup(users)
            return 0
        return _interactive(catalog, users, debug)
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    except Emerager0DBError as exc:
        print(f"Error: {exc}")
        return 1
