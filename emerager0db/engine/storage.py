"""On-disk file format for .edb databases and the account store.

Layout (big-endian header, then a UTF-8 JSON body):

    magic    4 bytes   b"EMDB"
    version  2 bytes   format version (currently 1)
    length   8 bytes   body length in bytes
    sha256   32 bytes  digest of the body, detects corruption and truncation
    body     JSON object with a "kind" field ("database" or "users")

Writes go to a temporary file in the same directory, are fsynced, and then atomically
renamed over the target. A crash leaves either the old file or the new file, never a mix.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any

from ..errors import CorruptDatabaseError

MAGIC = b"EMDB"
FORMAT_VERSION = 1
_HEADER = struct.Struct(">4sHQ32s")


def encode(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _HEADER.pack(MAGIC, FORMAT_VERSION, len(body), hashlib.sha256(body).digest()) + body


def decode(data: bytes) -> dict[str, Any]:
    if len(data) < _HEADER.size:
        raise CorruptDatabaseError("file is too short to be an Emerager0DB file")
    magic, version, length, digest = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise CorruptDatabaseError("not an Emerager0DB file (bad magic number)")
    if version > FORMAT_VERSION:
        raise CorruptDatabaseError(f"file format version {version} is newer than supported version {FORMAT_VERSION}")
    body = data[_HEADER.size:]
    if len(body) != length:
        raise CorruptDatabaseError("file is truncated or has trailing data")
    if hashlib.sha256(body).digest() != digest:
        raise CorruptDatabaseError("checksum mismatch: file is corrupted")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorruptDatabaseError("file body is not valid data") from exc
    if not isinstance(payload, dict):
        raise CorruptDatabaseError("file body has an unexpected structure")
    return payload


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return  # Directory fsync is unsupported on some platforms, including Windows.
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path: Path | str, data: bytes) -> None:
    """Replace path with data so readers never observe a partially written file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
    _fsync_directory(target.parent)


def write_database(path: Path | str, payload: dict[str, Any]) -> None:
    atomic_write(path, encode(payload))


def read_database(path: Path | str) -> dict[str, Any]:
    return decode(Path(path).read_bytes())
