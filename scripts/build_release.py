"""Build the standalone Emerager0DB executable for THIS platform and record its SHA-256.

Run it on each target platform (CI runs one job per platform). PyInstaller cannot cross-compile,
so each platform is built natively on a matching runner.

    pip install pyinstaller
    python scripts/build_release.py

Output:
    dist/Emerager0DB-<platform>[.exe]     the executable, named as the release manifest expects
    dist/SHA256SUMS.<platform>            one checksum line, merged into SHA256SUMS by the release job
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT))

from emerager0db.update import platform_key  # noqa: E402


def main() -> int:
    key = platform_key()
    suffix = ".exe" if os.name == "nt" else ""
    asset = f"Emerager0DB-{key}{suffix}"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--name",
            "Emerager0DB",
            "--paths",
            str(ROOT),
            "--clean",
            "--noconfirm",
            "--distpath",
            str(DIST),
            "--workpath",
            str(ROOT / "build"),
            "--specpath",
            str(ROOT / "build"),
            str(ROOT / "packaging" / "entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )

    built = DIST / f"Emerager0DB{suffix}"
    target = DIST / asset
    if target.exists():
        target.unlink()
    shutil.move(str(built), str(target))

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (DIST / f"SHA256SUMS.{key}").write_text(f"{digest}  {asset}\n", encoding="utf-8")
    print(f"Built {target}")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
