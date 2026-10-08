"""Password hashing with salted PBKDF2-HMAC-SHA256. Plaintext passwords are never stored."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

from .. import config
from ..errors import UserError

SCHEME = "pbkdf2_sha256"
MIN_PASSWORD_LENGTH = 8
_dummy_hash: str | None = None


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise UserError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def hash_password(password: str, iterations: int | None = None) -> str:
    """Return a self-describing hash string: scheme$iterations$salt$digest."""
    rounds = iterations or config.PBKDF2_ITERATIONS
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, rounds)
    return f"{SCHEME}${rounds}${base64.b64encode(salt).decode('ascii')}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds_text, salt_text, digest_text = encoded.split("$")
        rounds = int(rounds_text)
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(digest_text, validate=True)
    except (ValueError, binascii.Error):
        return False
    if scheme != SCHEME:
        return False
    return hmac.compare_digest(_derive(password, salt, rounds), expected)


def dummy_verify(password: str) -> None:
    """Spend the same time as a real verification so unknown usernames are not distinguishable by timing."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("unused-placeholder-password")
    verify_password(password, _dummy_hash)
