"""Update checks and verified self-update.

Only the update manifest is fetched from the network, and only over HTTPS. The release binary is
installed only after its SHA-256 matches the published SHA256SUMS. Databases and accounts live in
the data directory, which is never touched by an update.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import config
from .errors import UpdateError
from .version import __version__

MAX_MANIFEST_BYTES = 1_000_000


def platform_key() -> str:
    """Map this machine to a release key such as linux-x86_64 or macos-arm64."""
    os_name = {"windows": "windows", "linux": "linux", "darwin": "macos"}.get(platform.system().lower())
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine().lower()
    )
    if os_name is None or arch is None or (os_name == "windows" and arch == "arm64"):
        raise UpdateError(f"no release is published for {platform.system()} {platform.machine()}")
    return f"{os_name}-{arch}"


def parse_version(text: str) -> tuple[tuple[int, ...], int]:
    """Sort key where 0.1.0-beta sorts before 0.1.0."""
    core, _, prerelease = text.strip().partition("-")
    try:
        numbers = tuple(int(part) for part in core.split("."))
    except ValueError as exc:
        raise UpdateError(f"unrecognised version '{text}'") from exc
    numbers = numbers + (0,) * (3 - len(numbers))
    return numbers, 0 if prerelease else 1


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _get(url: str, timeout: float) -> bytes:
    if not url.startswith("https://"):
        raise UpdateError("refusing to contact a non-HTTPS address")
    request = urllib.request.Request(url, headers={"User-Agent": f"Emerager0DB/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        host = urllib.parse.urlsplit(url).netloc or "update server"
        raise UpdateError(f"could not reach {host}: {exc}") from exc


def fetch_manifest() -> dict[str, Any]:
    raw = _get(config.UPDATE_API_URL, config.UPDATE_TIMEOUT_SECONDS)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise UpdateError("update manifest is unexpectedly large")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("update manifest is not valid JSON") from exc
    for key in ("latest", "downloads", "checksums"):
        if key not in manifest:
            raise UpdateError(f"update manifest is missing '{key}'")
    return manifest


def check_for_update() -> str | None:
    """Return the newer version string if one exists. Network or format problems return None silently."""
    try:
        latest = fetch_manifest()["latest"]
        return latest if is_newer(latest, __version__) else None
    except UpdateError:
        return None


def expected_checksum(sums_text: str, filename: str) -> str:
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename:
            return parts[0].lower()
    raise UpdateError(f"no checksum is listed for {filename}")


def _replace_executable(staging: Path, executable: Path) -> None:
    if os.name != "nt":
        os.replace(staging, executable)
        return
    # Windows cannot overwrite a running executable, but it can rename one. Move the old file aside.
    previous = executable.with_name(executable.name + ".old")
    if previous.exists():
        try:
            previous.unlink()
        except OSError:
            pass
    os.replace(executable, previous)
    try:
        os.replace(staging, executable)
    except OSError:
        os.replace(previous, executable)
        raise


def perform_update() -> str | None:
    """Download, verify and install the latest release. Returns the new version, or None if current."""
    if not getattr(sys, "frozen", False):
        raise UpdateError(
            "self-update applies to standalone builds only. Reinstall with the installer or pip install -U emerager0db"
        )
    manifest = fetch_manifest()
    latest = manifest["latest"]
    if not is_newer(latest, __version__):
        return None
    key = platform_key()
    url = manifest["downloads"].get(key)
    if not url:
        raise UpdateError(f"no download is listed for {key}")
    filename = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
    sums = _get(manifest["checksums"], config.UPDATE_TIMEOUT_SECONDS).decode("utf-8", errors="replace")
    expected = expected_checksum(sums, filename)
    payload = _get(url, timeout=300)
    if hashlib.sha256(payload).hexdigest() != expected:
        raise UpdateError("downloaded file failed checksum verification. Nothing was changed.")
    executable = Path(sys.executable).resolve()
    staging = executable.with_name(executable.name + ".new")
    staging.write_bytes(payload)
    if os.name != "nt":
        staging.chmod(0o755)
    _replace_executable(staging, executable)
    return latest
