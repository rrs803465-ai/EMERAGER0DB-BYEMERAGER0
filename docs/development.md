# Development

## Setup

```sh
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Python 3.11 or newer is required. The engine has no runtime dependencies.

## Tests

```sh
python -m pytest -q
```

The suite covers the lexer and parser, every engine behavior in the SQL reference, permissions and accounts, backups and exports, the update logic, the web API routes, and an end-to-end run of the CLI. The test configuration lowers the password-hash cost so tests stay fast. Do not use that setting in production.

## Layout

See the architecture section of the README. The core rule is that each layer depends only on the layers below it:

```
cli -> commands -> session -> sql -> engine
                     \-> auth ->/
```

`engine` never imports `sql`, and `sql` never imports `cli`.

## Debugging

`Emerager0DB --debug` prints tracebacks for internal errors. Expected errors (bad SQL, permissions, constraints) always print a single `Error:` line.

## Building executables

PyInstaller cannot cross-compile, so build on each target:

```sh
pip install pyinstaller
python scripts/build_release.py
```

This writes `dist/Emerager0DB-<platform>[.exe]` and `dist/SHA256SUMS.<platform>`. Release builds happen in CI (`.github/workflows/release.yml`), with one job per platform.

## Website and API (Railway)

The web service lives in `web/`. Run it locally with:

```sh
python -m web.api.app          # serves on http://localhost:8080 (or $PORT)
```

It serves `/api/health`, `/api/version`, `/api/releases`, `/api/project`, the installers at `/get` and `/get.ps1`, and the static site from `web/frontend`. The Docker image contains only `web/` and `installer/`, so it cannot touch local databases.

## Storage format changes

Bump `FORMAT_VERSION` in `engine/storage.py` for any incompatible change to the body layout, and keep reading the old versions. Add a test that opens a file written by the previous version.
