"""Catalog: owns the data directory layout and hands out database objects."""

from __future__ import annotations

import threading
from pathlib import Path

from ..config import DATABASE_EXTENSION
from ..errors import DatabaseExistsError, DatabaseNotFoundError
from ..names import validate_identifier
from . import storage
from .database import Database


class Catalog:
    """Layout:

        <root>/databases/<name>.edb   one file per database
        <root>/system/users.json      account store
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.databases_dir = self.root / "databases"
        self.system_dir = self.root / "system"
        self._cache: dict[str, Database] = {}
        self._lock = threading.RLock()

    def ensure_layout(self) -> None:
        self.databases_dir.mkdir(parents=True, exist_ok=True)
        self.system_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        validate_identifier(name, "database name")
        return self.databases_dir / f"{name.lower()}{DATABASE_EXTENSION}"

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def list_databases(self) -> list[str]:
        if not self.databases_dir.exists():
            return []
        return sorted(path.stem for path in self.databases_dir.glob(f"*{DATABASE_EXTENSION}"))

    def create_database(self, name: str, owner: str) -> Database:
        with self._lock:
            path = self._path(name)
            if path.exists():
                raise DatabaseExistsError(f"database '{name}' already exists")
            database = Database(name, owner, path=path)
            database.save()
            self._cache[name.lower()] = database
            return database

    def open_database(self, name: str) -> Database:
        with self._lock:
            key = name.lower()
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            path = self._path(name)
            if not path.exists():
                raise DatabaseNotFoundError(f"database '{name}' does not exist")
            database = Database.load(path)
            self._cache[key] = database
            return database

    def drop_database(self, name: str) -> None:
        with self._lock:
            path = self._path(name)
            if not path.exists():
                raise DatabaseNotFoundError(f"database '{name}' does not exist")
            path.unlink()
            self._cache.pop(name.lower(), None)

    def backup_database(self, name: str, destination: Path | str) -> Path:
        """Copy the committed on-disk state of a database. The copy is verified before it is written."""
        with self._lock:
            source = self._path(name)
            if not source.exists():
                raise DatabaseNotFoundError(f"database '{name}' does not exist")
            data = source.read_bytes()
            storage.decode(data)
            target = Path(destination)
            storage.atomic_write(target, data)
            return target

    def import_database(self, source: Path | str, owner: str, name: str | None = None) -> Database:
        """Load a .edb file from elsewhere into the catalog under a new name, owned by owner."""
        data = Path(source).read_bytes()
        payload = storage.decode(data)
        if payload.get("kind") != "database":
            raise DatabaseNotFoundError(f"'{source}' is not an Emerager0DB database")
        target_name = name or payload["name"]
        with self._lock:
            path = self._path(target_name)
            if path.exists():
                raise DatabaseExistsError(f"database '{target_name}' already exists")
            payload["name"] = target_name
            payload["owner"] = owner
            database = Database.from_dict(payload, path=path)
            database.save()
            self._cache[target_name.lower()] = database
            return database
