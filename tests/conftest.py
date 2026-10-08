"""Test configuration. Lower the password-hash cost and disable the network update check before import."""

import os

os.environ.setdefault("EMERAGER0DB_PBKDF2_ITERATIONS", "1000")
os.environ.setdefault("EMERAGER0DB_NO_UPDATE_CHECK", "1")
