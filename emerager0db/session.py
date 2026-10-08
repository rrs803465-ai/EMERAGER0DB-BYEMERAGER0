"""Connections. A Connection runs SQL as one Principal, tracks the current database and owns transactions.

Two modes:
  * Catalog mode (CLI and server use): supports CREATE/DROP/USE DATABASE, GRANT and user management.
  * Single-file mode (embedded Python API): one .edb file, no login, trusted local process.
"""

from __future__ import annotations

from typing import Iterator, Sequence

from .auth import permissions as perm
from .auth.permissions import DATABASE_GRANTS, Permission, Principal
from .auth.users import User, UserStore
from .engine.catalog import Catalog
from .engine.database import Database
from .engine.transaction import Transaction
from .errors import (
    AuthenticationError,
    Emerager0DBError,
    PermissionDeniedError,
    TransactionError,
    UserError,
)
from .sql import ast as A
from .sql.executor import Executor, Result
from .sql.parser import Parser


class Connection:
    def __init__(
        self,
        principal: Principal,
        *,
        catalog: Catalog | None = None,
        users: UserStore | None = None,
        database: Database | None = None,
    ) -> None:
        self.principal = principal
        self.catalog = catalog
        self.users = users
        self.current: Database | None = database
        self._transaction: Transaction | None = None

    # ----- construction ---------------------------------------------------

    @classmethod
    def login(cls, catalog: Catalog, users: UserStore, username: str, password: str) -> "Connection":
        user: User = users.authenticate(username, password)
        return cls(user.principal(), catalog=catalog, users=users)

    # ----- properties -----------------------------------------------------

    @property
    def current_database(self) -> str | None:
        return self.current.name if self.current is not None else None

    @property
    def in_transaction(self) -> bool:
        return self._transaction is not None

    # ----- SQL execution --------------------------------------------------

    def execute(self, sql: str, params: Sequence[object] = ()) -> Result:
        """Run one or more statements and return the result of the last one."""
        last = Result()
        for result in self.iter_script(sql, params):
            last = result
        return last

    def execute_script(self, sql: str, params: Sequence[object] = ()) -> list[Result]:
        return list(self.iter_script(sql, params))

    def iter_script(self, sql: str, params: Sequence[object] = ()) -> Iterator[Result]:
        """Parse the whole script first (so syntax errors run nothing), then yield each result as it completes."""
        statements = Parser(sql, params).parse()
        for statement in statements:
            yield self._run(statement)

    def _run(self, statement: A.Statement) -> Result:
        if isinstance(statement, A.CreateDatabase):
            return self._create_database(statement)
        if isinstance(statement, A.DropDatabase):
            return self._drop_database(statement)
        if isinstance(statement, A.UseDatabase):
            return self._use(statement)
        if isinstance(statement, A.Grant):
            return self._grant(statement)
        if isinstance(statement, A.Begin):
            return self._begin()
        if isinstance(statement, A.Commit):
            return self._commit()
        if isinstance(statement, A.Rollback):
            return self._rollback()
        database = self._require_database()
        result = Executor(database, self.principal, self._admin_names()).run(statement)
        if result.mutated and self._transaction is None:
            self._persist(database)
        return result

    # ----- helpers --------------------------------------------------------

    def _admin_names(self) -> frozenset[str]:
        return frozenset(self.users.admin_names()) if self.users is not None else frozenset()

    def _require_catalog(self) -> Catalog:
        if self.catalog is None:
            raise Emerager0DBError("database statements are not available on a single-file connection")
        return self.catalog

    def _require_database(self) -> Database:
        if self.current is None:
            raise Emerager0DBError("no database selected. Use: USE <name>;")
        return self.current

    def _persist(self, database: Database) -> None:
        if database.path is None:
            return
        try:
            database.save()
        except OSError as exc:
            self._reload(database)
            raise Emerager0DBError(f"could not write '{database.path}': {exc}") from exc

    @staticmethod
    def _reload(database: Database) -> None:
        """After a failed write, restore in-memory state from the last good file so memory and disk agree."""
        if database.path is None or not database.path.exists():
            return
        fresh = Database.load(database.path)
        database.tables, database.grants = fresh.tables, fresh.grants

    # ----- database statements ---------------------------------------------

    def _create_database(self, s: A.CreateDatabase) -> Result:
        catalog = self._require_catalog()
        if not perm.can_create_database(self.principal):
            raise PermissionDeniedError("permission denied: create databases")
        if catalog.exists(s.name) and s.if_not_exists:
            return Result(message=f"Database '{s.name}' already exists.")
        catalog.create_database(s.name, owner=self.principal.name)
        return Result(message="Database created.")

    def _drop_database(self, s: A.DropDatabase) -> Result:
        catalog = self._require_catalog()
        if not catalog.exists(s.name) and s.if_exists:
            return Result(message=f"Database '{s.name}' does not exist.")
        database = catalog.open_database(s.name)
        if not perm.can_drop_database(self.principal, database, self._admin_names()):
            raise PermissionDeniedError(f"permission denied: drop database '{database.name}'")
        if self.current is not None and self.current.name.lower() == database.name.lower():
            if self._transaction is not None:
                raise TransactionError("COMMIT or ROLLBACK before dropping the current database")
            self.current = None
        catalog.drop_database(database.name)
        return Result(message=f"Database '{database.name}' dropped.")

    def _use(self, s: A.UseDatabase) -> Result:
        catalog = self._require_catalog()
        if self._transaction is not None:
            raise TransactionError("COMMIT or ROLLBACK before switching databases")
        database = catalog.open_database(s.name)
        if not perm.can_read_database(self.principal, database):
            raise PermissionDeniedError(f"permission denied: use database '{database.name}'")
        self.current = database
        return Result(message=f"Using database '{database.name}'.")

    def _grant(self, s: A.Grant) -> Result:
        catalog = self._require_catalog()
        database = catalog.open_database(s.database)
        if not perm.can_manage_grants(self.principal, database):
            raise PermissionDeniedError(f"permission denied: manage grants on '{database.name}'")
        if s.permission not in DATABASE_GRANTS:
            raise Emerager0DBError(
                f"unknown permission '{s.permission}'; expected one of {', '.join(DATABASE_GRANTS)}"
            )
        target = s.user.lower()
        if self.users is not None and self.users.get(target) is None:
            raise UserError(f"user '{s.user}' does not exist")
        granted = DATABASE_GRANTS[s.permission].value
        grants = database.grants.setdefault(target, set())
        if s.revoke:
            grants.discard(granted)
        else:
            grants.add(granted)
        if not grants:
            database.grants.pop(target, None)
        self._persist(database)
        if s.revoke:
            return Result(message=f"Revoked {s.permission} on '{database.name}' from '{target}'.")
        return Result(message=f"Granted {s.permission} on '{database.name}' to '{target}'.")

    # ----- transactions -----------------------------------------------------

    def _begin(self) -> Result:
        database = self._require_database()
        if self._transaction is not None:
            raise TransactionError("a transaction is already in progress")
        self._transaction = Transaction(database)
        return Result(message="Transaction started.")

    def _commit(self) -> Result:
        if self._transaction is None:
            raise TransactionError("no transaction in progress")
        database = self._transaction.database
        try:
            self._persist(database)
        except Emerager0DBError:
            self._transaction.rollback()
            self._transaction = None
            raise
        self._transaction = None
        return Result(message="Transaction committed.")

    def _rollback(self) -> Result:
        if self._transaction is None:
            raise TransactionError("no transaction in progress")
        self._transaction.rollback()
        self._transaction = None
        return Result(message="Transaction rolled back.")

    # ----- account management -----------------------------------------------

    def _require_users(self) -> UserStore:
        if self.users is None:
            raise Emerager0DBError("account management is not available on a single-file connection")
        return self.users

    def _require_user_manage(self) -> None:
        if not perm.can_manage_users(self.principal):
            raise PermissionDeniedError("permission denied: manage user accounts")

    def list_users(self) -> list[User]:
        return self._require_users().list()

    def create_user(self, name: str, password: str, *, admin: bool = False) -> None:
        store = self._require_users()
        self._require_user_manage()
        granted = {Permission.ADMIN.value} if admin else set()
        store.create(name, password, granted)

    def delete_user(self, name: str) -> None:
        store = self._require_users()
        self._require_user_manage()
        store.delete(name)

    def change_password(self, name: str, new_password: str, *, current_password: str | None = None) -> None:
        """Users change their own password by proving the current one. Managing others requires USER_MANAGE."""
        store = self._require_users()
        if name.lower() == self.principal.name:
            if current_password is None or not store.verify(self.principal.name, current_password):
                raise AuthenticationError("current password is incorrect")
        else:
            self._require_user_manage()
        store.set_password(name, new_password)

    def list_databases(self) -> list[str]:
        catalog = self._require_catalog()
        names = []
        for name in catalog.list_databases():
            database = catalog.open_database(name)
            if perm.can_read_database(self.principal, database):
                names.append(database.name)
        return names

    def backup(self, destination: str) -> str:
        """Write a verified copy of the current database's committed state to destination."""
        database = self._require_database()
        if database.path is None:
            raise Emerager0DBError("this database is in memory and cannot be backed up")
        self._require_catalog().backup_database(database.name, destination)
        return destination

