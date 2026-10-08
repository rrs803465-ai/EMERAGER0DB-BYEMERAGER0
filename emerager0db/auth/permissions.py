"""Permission model.

Accounts hold global permissions (for example DATABASE_CREATE or USER_MANAGE). Databases hold
grants per user (DATABASE_READ, DATABASE_WRITE, TABLE_CREATE, TABLE_DROP). The database owner
has every grant on that database. Administrators (ADMIN) bypass every check.

Protected objects: a table or database owned by an administrator can only be dropped by an
administrator, so normal users cannot delete root-owned data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..engine.database import Database
from ..engine.table import Table


class Permission(str, Enum):
    DATABASE_CREATE = "DATABASE_CREATE"
    DATABASE_DROP = "DATABASE_DROP"
    DATABASE_READ = "DATABASE_READ"
    DATABASE_WRITE = "DATABASE_WRITE"
    TABLE_CREATE = "TABLE_CREATE"
    TABLE_DROP = "TABLE_DROP"
    TABLE_READ = "TABLE_READ"
    TABLE_WRITE = "TABLE_WRITE"
    USER_MANAGE = "USER_MANAGE"
    ADMIN = "ADMIN"


ALL_PERMISSIONS = frozenset(permission.value for permission in Permission)
DATABASE_GRANTS = {
    "READ": Permission.DATABASE_READ,
    "WRITE": Permission.DATABASE_WRITE,
    "TABLE_CREATE": Permission.TABLE_CREATE,
    "TABLE_DROP": Permission.TABLE_DROP,
}


@dataclass(frozen=True)
class Principal:
    """The authenticated identity a connection acts as."""

    name: str
    permissions: frozenset[str] = frozenset()

    @property
    def is_admin(self) -> bool:
        return Permission.ADMIN.value in self.permissions

    def has(self, permission: Permission) -> bool:
        return self.is_admin or permission.value in self.permissions


def _granted(principal: Principal, database: Database, permission: Permission) -> bool:
    return permission.value in database.grants.get(principal.name, set())


def can_create_database(principal: Principal) -> bool:
    return principal.has(Permission.DATABASE_CREATE)


def can_drop_database(principal: Principal, database: Database, admin_names: frozenset[str]) -> bool:
    if principal.is_admin or database.owner == principal.name:
        return True
    if database.owner in admin_names:
        return False
    return principal.has(Permission.DATABASE_DROP)


def can_read_database(principal: Principal, database: Database) -> bool:
    return (
        principal.is_admin
        or database.owner == principal.name
        or _granted(principal, database, Permission.DATABASE_READ)
        or principal.has(Permission.TABLE_READ)
    )


def can_write_database(principal: Principal, database: Database) -> bool:
    return (
        principal.is_admin
        or database.owner == principal.name
        or _granted(principal, database, Permission.DATABASE_WRITE)
        or principal.has(Permission.TABLE_WRITE)
    )


def can_create_table(principal: Principal, database: Database) -> bool:
    return (
        principal.is_admin
        or database.owner == principal.name
        or _granted(principal, database, Permission.TABLE_CREATE)
        or principal.has(Permission.TABLE_CREATE)
    )


def can_drop_table(
    principal: Principal, database: Database, table: Table, admin_names: frozenset[str]
) -> bool:
    if principal.is_admin or table.owner == principal.name:
        return True
    if table.owner in admin_names:
        return False
    if database.owner == principal.name:
        return True
    return _granted(principal, database, Permission.TABLE_DROP) or principal.has(Permission.TABLE_DROP)


def can_manage_grants(principal: Principal, database: Database) -> bool:
    return principal.is_admin or database.owner == principal.name


def can_manage_users(principal: Principal) -> bool:
    return principal.has(Permission.USER_MANAGE)
