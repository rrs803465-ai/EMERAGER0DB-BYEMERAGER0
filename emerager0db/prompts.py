"""Input helpers. Passwords are read without echo on a terminal and from stdin when piped."""

from __future__ import annotations

import getpass
import sys


def read_line(prompt: str) -> str:
    """Read one line of visible input, stripped of surrounding whitespace."""
    return input(prompt).strip()


def read_secret(prompt: str) -> str:
    """Read a secret without echoing it. The value is never printed or logged."""
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    print(prompt, end="", flush=True)
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\r\n")
