"""Runtime configuration, resolved from environment variables with safe defaults."""

from __future__ import annotations

import os
from pathlib import Path

# The Railway deployment injects the real repository URL through this variable.
REPO_URL = os.environ.get("EMERAGER0DB_REPO_URL", "https://github.com/rrs803465-ai/EMERAGER0DB-BYEMERAGER0")
UPDATE_API_URL = os.environ.get("EMERAGER0DB_UPDATE_URL", "https://falks.cyou/api/version")
WEBSITE_URL = "https://falks.cyou"
DATABASE_EXTENSION = ".edb"
UPDATE_TIMEOUT_SECONDS = 3.0
UPDATE_CHECK_ENABLED = os.environ.get("EMERAGER0DB_NO_UPDATE_CHECK", "") not in ("1", "true", "yes")
PBKDF2_ITERATIONS = int(os.environ.get("EMERAGER0DB_PBKDF2_ITERATIONS", "600000"))
DEBUG = os.environ.get("EMERAGER0DB_DEBUG", "") not in ("", "0", "false", "no")


def data_dir() -> Path:
    """Return the directory holding databases and accounts (EMERAGER0DB_HOME or ~/.emerager0db)."""
    override = os.environ.get("EMERAGER0DB_HOME")
    return Path(override) if override else Path.home() / ".emerager0db"
