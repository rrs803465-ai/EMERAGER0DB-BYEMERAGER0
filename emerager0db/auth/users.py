"""Account store, kept in <data>/system/users.json using the same checksummed file envelope."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..engine import storage
from ..errors import AuthenticationError, CorruptDatabaseError, UserError
from .passwords import dummy_verify, hash_password, validate_password, verify_password
from .permissions import ALL_PERMISSIONS, Permission, Principal

_USERNAME = re.compile(r"^[a-z][a-z0-9_.-]{0,31}$")


def is_valid_username(name: str) -> bool:
    return bool(_USERNAME.match(name))


@dataclass
class User:
    name: str
    password_hash: str
    permissions: set[str] = field(default_factory=set)
    is_root: bool = False
    created_at: int = 0

    @property
    def is_admin(self) -> bool:
        return Permission.ADMIN.value in self.permissions

    def principal(self) -> Principal:
        return Principal(self.name, frozenset(self.permissions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "password_hash": self.password_hash,
            "permissions": sorted(self.permissions),
            "is_root": self.is_root,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        return cls(
            name=data["name"],
            password_hash=data["password_hash"],
            permissions=set(data["permissions"]),
            is_root=bool(data.get("is_root", False)),
            created_at=int(data.get("created_at", 0)),
        )


class UserStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._users: dict[str, User] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = storage.read_database(self.path)
        if payload.get("kind") != "users":
            raise CorruptDatabaseError("account store is malformed")
        self._users = {entry["name"]: User.from_dict(entry) for entry in payload["users"]}

    def _save(self) -> None:
        payload = {
            "kind": "users",
            "users": [user.to_dict() for user in sorted(self._users.values(), key=lambda u: u.name)],
        }
        storage.write_database(self.path, payload)

    def _require(self, name: str) -> User:
        user = self.get(name)
        if user is None:
            raise UserError(f"user '{name}' does not exist")
        return user

    def has_users(self) -> bool:
        return bool(self._users)

    def get(self, name: str) -> User | None:
        return self._users.get(name.lower())

    def list(self) -> list[User]:
        return sorted(self._users.values(), key=lambda user: user.name)

    def admin_names(self) -> set[str]:
        return {user.name for user in self._users.values() if user.is_admin}

    def create(
        self,
        name: str,
        password: str,
        permissions: Iterable[str] = (),
        *,
        root: bool = False,
    ) -> User:
        key = name.lower()
        if not is_valid_username(key):
            raise UserError(
                "usernames use lowercase letters, digits, '_', '.' and '-', and start with a letter"
            )
        if key in self._users:
            raise UserError(f"user '{key}' already exists")
        if root and any(user.is_root for user in self._users.values()):
            raise UserError("a root account already exists")
        granted = set(permissions)
        unknown = granted - ALL_PERMISSIONS
        if unknown:
            raise UserError(f"unknown permission: {', '.join(sorted(unknown))}")
        validate_password(password)
        user = User(
            name=key,
            password_hash=hash_password(password),
            permissions=granted,
            is_root=root,
            created_at=int(time.time()),
        )
        self._users[key] = user
        self._save()
        return user

    def delete(self, name: str) -> None:
        user = self._require(name)
        if user.is_root:
            raise UserError("the root account cannot be deleted")
        if user.is_admin and len(self.admin_names()) == 1:
            raise UserError("cannot delete the last administrator")
        del self._users[user.name]
        self._save()

    def set_password(self, name: str, password: str) -> None:
        user = self._require(name)
        validate_password(password)
        user.password_hash = hash_password(password)
        self._save()

    def grant(self, name: str, permission: str) -> None:
        user = self._require(name)
        if permission not in ALL_PERMISSIONS:
            raise UserError(f"unknown permission: {permission}")
        user.permissions.add(permission)
        self._save()

    def revoke(self, name: str, permission: str) -> None:
        user = self._require(name)
        if permission == Permission.ADMIN.value and user.is_admin and len(self.admin_names()) == 1:
            raise UserError("cannot revoke ADMIN from the last administrator")
        user.permissions.discard(permission)
        self._save()

    def verify(self, name: str, password: str) -> bool:
        user = self.get(name)
        if user is None:
            dummy_verify(password)
            return False
        return verify_password(password, user.password_hash)

    def authenticate(self, name: str, password: str) -> User:
        user = self.get(name)
        if user is None:
            dummy_verify(password)
            raise AuthenticationError("invalid username or password")
        if not verify_password(password, user.password_hash):
            raise AuthenticationError("invalid username or password")
        return user
