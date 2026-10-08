# Contributing to Emerager0DB

Thanks for helping. Emerager0DB is a database engine, so correctness matters more than feature count.

## Ground rules

- Do not wrap `sqlite3` or any other database. The storage engine, SQL parser and executor are our own code.
- No plaintext passwords, `eval`/`exec` on user input, or string-built SQL. Use parameters.
- Every bug fix ships with a test that fails before the fix.
- Keep the core engine dependency-free. Standard library only.
- Error messages must be readable by a normal user. Never let a traceback reach the CLI.

## Workflow

1. Fork and branch from `main`.
2. Set up a virtual environment and install the dev extras:

       python -m venv .venv
       . .venv/bin/activate          # Windows: .venv\Scripts\activate
       pip install -e ".[dev]"

3. Run the tests: `python -m pytest -q`
4. Keep commits focused. Describe what changed and why in the message.
5. Open a pull request. Explain any change to the file format, the SQL grammar, or permissions, because those affect existing databases.

## Format changes

Changes to `engine/storage.py` or the table JSON layout must bump `FORMAT_VERSION` and keep reading older versions. A release that cannot open existing `.edb` files is not acceptable.

## Security issues

Do not open a public issue for a vulnerability. Contact the maintainers privately first.
