"""Status report. Every value is read from live engine state, nothing is estimated."""

from __future__ import annotations

from ..session import Connection
from ..version import __version__


def status_lines(connection: Connection) -> list[str]:
    database = connection.current
    principal = connection.principal
    lines = ["Emerager0DB Status", "------------------", f"Version: {__version__}"]
    if database is not None:
        lines.append(f"Database: {database.name}")
        lines.append(f"Tables: {len(database.tables)}")
        lines.append(f"Database size: {database.size_on_disk() / 1024:.1f} KB")
    else:
        lines.append("Database: (none selected)")
    lines.append(f"User: {principal.name}")
    lines.append(f"Role: {'administrator' if principal.is_admin else 'user'}")
    lines.append(f"Transaction: {'open' if connection.in_transaction else 'none'}")
    lines.append("Engine: online")
    return lines
