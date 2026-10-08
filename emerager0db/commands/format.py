"""Plain terminal formatting: aligned columns, NULL shown as NULL, no colours or decoration."""

from __future__ import annotations

from typing import Any, Sequence

from ..sql.executor import Result


def _cell(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_table(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [[_cell(value) for value in row] for row in rows]
    widths = [len(name) for name in columns]
    for row in cells:
        for i, text in enumerate(row):
            widths[i] = max(widths[i], len(text))
    header = " | ".join(name.ljust(width) for name, width in zip(columns, widths))
    separator = "-+-".join("-" * width for width in widths)
    body = [" | ".join(text.ljust(width) for text, width in zip(row, widths)) for row in cells]
    return "\n".join([header, separator, *body])


def format_result(result: Result) -> str:
    if result.columns:
        count = len(result.rows)
        noun = "row" if count == 1 else "rows"
        return f"{render_table(result.columns, result.rows)}\n({count} {noun})"
    return result.message or ""
