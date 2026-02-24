import openpyxl
from DIGEST_APP.APP.dto import DescriptionOfNewTask, RuntimeContext, DigestConfig
from pathlib import Path
from typing import Any

from _pytest.monkeypatch import MonkeyPatch

from DIGEST_APP.CONFIG.config import ExcelConfig
from DIGEST_APP.APP.SERVICES.output_report import OutputReport


def d(task: str, component: str | list[str]) -> DescriptionOfNewTask:
    if isinstance(component, str):
        component = [component]

    return DescriptionOfNewTask(
        task=task,
        description="B",
        first_solution="C",
        components=component,
        what_has_changed="D",
        how_it_changed="E",
    )


def get_by_task(items: list[DescriptionOfNewTask], task: str) -> DescriptionOfNewTask:
    try:
        return next(x for x in items if x.task == task)
    except StopIteration:
        raise AssertionError(
            f"Задача '{task}' не найдена." f"Доступные задачи {[x.task for x in items]}"
        )


def make_ctx(excel_path: Path) -> RuntimeContext:
    return RuntimeContext(
        app=DigestConfig(
            local_dir=excel_path.parent,
            excel=ExcelConfig(excel_path=excel_path),
        )
    )


def make_descriptions() -> list[DescriptionOfNewTask]:
    return [
        d(task="Раз", component=["G_1", "G_2", "G_3"]),
        d(task="Два", component="F_1"),
    ]


def read_excel_rows(excel_path: Path, values_only: bool) -> list[tuple[Any, ...]]:
    wb = openpyxl.load_workbook(excel_path, read_only=values_only)
    try:
        ws = wb.active
        return list(ws.iter_rows(values_only=values_only)) if ws is not None else list()
    finally:
        wb.close()


def create_report(
        tmp_path: Path, monkeypatch: MonkeyPatch, descriptions: list[DescriptionOfNewTask]
) -> tuple[RuntimeContext, Path]:
    excel_path = tmp_path / "test_digest.xlsx"
    ctx = make_ctx(excel_path=excel_path)
    report = OutputReport()
    monkeypatch.setattr(report, "open_file", lambda _: True)

    report.run(ctx=ctx, descriptions=descriptions)

    return ctx, excel_path
