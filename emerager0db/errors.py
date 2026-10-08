"""Exception hierarchy. Every class derives from Emerager0DBError, whose message is safe to show users."""

from __future__ import annotations


class Emerager0DBError(Exception):
    """Base class for all expected, user-facing errors."""


class SQLSyntaxError(Emerager0DBError):
    """The SQL text could not be tokenized or parsed."""


class ParameterError(Emerager0DBError):
    """Bound parameters do not match the placeholders in the SQL text."""


class DataTypeError(Emerager0DBError):
    """A value does not match a column type, or two values cannot be compared."""


class ConstraintError(Emerager0DBError):
    """A NOT NULL, PRIMARY KEY, UNIQUE or structural constraint was violated."""


class TableNotFoundError(Emerager0DBError):
    """The referenced table does not exist."""


class TableExistsError(Emerager0DBError):
    """A table with this name already exists."""


class ColumnNotFoundError(Emerager0DBError):
    """The referenced column does not exist."""


class IndexExistsError(Emerager0DBError):
    """An index with this name already exists on the table."""


class IndexNotFoundError(Emerager0DBError):
    """The referenced index does not exist."""


class DatabaseNotFoundError(Emerager0DBError):
    """The referenced database does not exist."""


class DatabaseExistsError(Emerager0DBError):
    """A database with this name already exists."""


class PermissionDeniedError(Emerager0DBError):
    """The current account lacks the permission required for this action."""


class AuthenticationError(Emerager0DBError):
    """Login failed."""


class UserError(Emerager0DBError):
    """An account-management request is invalid (duplicate name, weak password, protected account)."""


class CorruptDatabaseError(Emerager0DBError):
    """A database or account file failed format or checksum validation."""


class TransactionError(Emerager0DBError):
    """A transaction command was used in an invalid state."""


class UpdateError(Emerager0DBError):
    """An update check or self-update could not be completed."""
