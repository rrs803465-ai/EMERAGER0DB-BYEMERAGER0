"""Identifier rules shared by the SQL parser and the catalog."""

from __future__ import annotations

import re

from .errors import Emerager0DBError

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


def validate_identifier(name: str, kind: str) -> str:
    """Return name unchanged if it is a legal identifier, otherwise raise Emerager0DBError.

    Identifiers start with a letter, contain letters, digits and underscores, and are at most
    63 characters. Leading double underscores are reserved for internal objects such as
    automatically created indexes.
    """
    if not _IDENTIFIER.match(name):
        raise Emerager0DBError(
            f"invalid {kind} '{name}': use letters, digits and underscores, starting with a letter"
        )
    return name
