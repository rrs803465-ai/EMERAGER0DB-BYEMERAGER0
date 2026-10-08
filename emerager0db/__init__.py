"""Emerager0DB: a lightweight SQL database engine written in Python.

Embedded use (single .edb file, trusted local process):

    from emerager0db import connect
    db = connect("school.edb")
    db.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    db.execute("INSERT INTO users VALUES (?, ?)", (1, "Rrs"))
    rows = db.execute("SELECT * FROM users").fetchall()
"""

from __future__ import annotations

from pathlib import Path

from .auth.permissions import Permission, Principal
from .engine.database import Database
from .session import Connection
from .version import __version__

LOCAL_PRINCIPAL = Principal(name="local", permissions=frozenset({Permission.ADMIN.value}))


def connect(path: str | Path) -> Connection:
    """Open or create a single .edb file. No login is performed: the caller is the local operator."""
    file_path = Path(path)
    if file_path.exists():
        database = Database.load(file_path)
    else:
        database = Database(file_path.stem, owner="local", path=file_path)
        database.save()
    return Connection(LOCAL_PRINCIPAL, database=database)


__all__ = ["connect", "Connection", "__version__"]
