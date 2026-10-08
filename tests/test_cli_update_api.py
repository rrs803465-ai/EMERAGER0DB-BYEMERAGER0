import json
import os
import subprocess
import sys

import pytest

from emerager0db import update
from emerager0db.errors import UpdateError
from web.api import app as web_app


def test_version_ordering_treats_beta_as_prerelease():
    assert update.is_newer("0.2.0", "0.1.0-beta")
    assert update.is_newer("0.1.0", "0.1.0-beta")
    assert not update.is_newer("0.1.0-beta", "0.1.0-beta")
    assert not update.is_newer("0.0.9", "0.1.0-beta")


def test_expected_checksum_reads_sha256sums_format():
    sums = "abc123  Emerager0DB-linux-x86_64\nfff000  Emerager0DB-macos-arm64\n"
    assert update.expected_checksum(sums, "Emerager0DB-linux-x86_64") == "abc123"
    with pytest.raises(UpdateError):
        update.expected_checksum(sums, "Emerager0DB-windows-x86_64.exe")


def test_platform_key_mapping(monkeypatch):
    monkeypatch.setattr(update.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(update.platform, "machine", lambda: "arm64")
    assert update.platform_key() == "macos-arm64"
    monkeypatch.setattr(update.platform, "system", lambda: "Linux")
    monkeypatch.setattr(update.platform, "machine", lambda: "aarch64")
    assert update.platform_key() == "linux-arm64"


def test_update_check_fails_quietly_when_offline(monkeypatch):
    def offline(url, timeout):
        raise UpdateError("offline")

    monkeypatch.setattr(update, "_get", offline)
    assert update.check_for_update() is None


def test_update_check_reports_newer_release(monkeypatch):
    manifest = {
        "latest": "0.2.0",
        "downloads": {"linux-x86_64": "https://example.invalid/Emerager0DB-linux-x86_64"},
        "checksums": "https://example.invalid/SHA256SUMS",
    }
    monkeypatch.setattr(update, "_get", lambda url, timeout: json.dumps(manifest).encode())
    assert update.check_for_update() == "0.2.0"


def test_non_https_update_urls_are_refused():
    with pytest.raises(UpdateError):
        update._get("http://example.invalid/api", 1.0)


def test_api_health_and_version_routes():
    status, body = web_app.api_response("/api/health")
    assert status == 200 and body["status"] == "ok"
    status, body = web_app.api_response("/api/version")
    assert status == 200
    assert body["latest"] and "downloads" in body and "checksums" in body


def test_api_unknown_route_is_404():
    status, _ = web_app.api_response("/api/nope")
    assert status == 404


def test_cli_end_to_end_setup_login_and_queries(tmp_path):
    home = tmp_path / "home"
    script = "\n".join(
        [
            "rrs",
            "rootpass123",
            "rootpass123",
            "n",
            "rrs",
            "rootpass123",
            "CREATE DATABASE school;",
            "USE school;",
            "CREATE TABLE students (id INTEGER, name TEXT, age INTEGER);",
            "INSERT INTO students (id, name) VALUES (1, 'Rrs');",
            "SELECT * FROM students;",
            "UPDATE students SET age = 13 WHERE age IS NULL;",
            "SELECT * FROM students;",
            ".status",
            ".exit",
        ]
    ) + "\n"
    env = dict(os.environ, EMERAGER0DB_HOME=str(home))
    proc = subprocess.run(
        [sys.executable, "-m", "emerager0db", "--data-dir", str(home)],
        input=script,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    output = proc.stdout
    assert proc.returncode == 0, proc.stderr
    assert "Database created." in output
    assert "Table created." in output
    assert "1  | Rrs  | NULL" in output
    assert "1 row(s) updated." in output
    assert "Engine: online" in output
    assert "Version 0.1 beta" in output
    assert "rootpass123" not in output
    assert "Traceback" not in output + proc.stderr


def test_cli_version_subcommand(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "emerager0db", "version"],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=60,
    )
    assert proc.returncode == 0
    assert "0.1.0-beta" in proc.stdout
