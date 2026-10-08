"""PyInstaller entry point. Uses an absolute import, which frozen builds require."""

from emerager0db.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
