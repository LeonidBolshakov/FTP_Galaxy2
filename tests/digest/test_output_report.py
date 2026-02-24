from pathlib import Path
from typing import Any

from _pytest.monkeypatch import MonkeyPatch

from DIGEST_APP.APP.dto import RuntimeContext, DescriptionOfNewTask
from tests.utils import make_descriptions, read_excel_rows, create_report


def test_creates_xlsx_with_expected_valus(
        tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    descriptions = make_descriptions()
    ctx, excel_path = create_report(
        tmp_path=tmp_path, monkeypatch=monkeypatch, descriptions=descriptions
    )

    rows = read_excel_rows(excel_path=excel_path, values_only=True)
    assert_header(ctx, rows)
    assert_row(row=rows[1], descr=descriptions[0])
    assert_row(row=rows[2], descr=descriptions[1])

    rows = read_excel_rows(excel_path=excel_path, values_only=False)
    assert_columns_width(ctx, rows)


def assert_header(ctx: RuntimeContext, rows: list[tuple[Any, ...]]) -> None:
    exepted = tuple(col.header for col in ctx.app.excel.columns)
    actual = rows[0]
    assert actual == exepted


def assert_row(row: tuple[Any, ...], descr: DescriptionOfNewTask) -> None:
    expected = (
        descr.task,
        ", ".join(descr.components),
        descr.description,
        descr.what_has_changed,
        descr.how_it_changed,
    )
    actual = row
    assert actual == expected


def assert_columns_width(ctx: RuntimeContext, rows: list[tuple[Any, ...]]) -> None:
    columns = ctx.app.excel.columns
    expected_widths = [column.width for column in columns]

    actual_widths = []
    for cell in rows[0]:
        ws = cell.parent
        column_letter = cell.column_letter
        actual_widths.append(ws.column_dimensions[column_letter].width)

    assert expected_widths == actual_widths


def test_creates_xlsx_with_empty_valu(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    descriptions: list[DescriptionOfNewTask] = []
    ctx, excel_path = create_report(
        tmp_path=tmp_path, monkeypatch=monkeypatch, descriptions=descriptions
    )
    rows = read_excel_rows(excel_path=excel_path, values_only=True)
    assert len(rows) == 1
