from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from DIGEST_APP.APP.controller import DigestController
from DIGEST_APP.APP.dto import RuntimeContext, DescriptionOfNewTask
from DIGEST_APP.APP.SERVICES.output_report import OutputReport
from DIGEST_APP.CONFIG.config import (
    ExcelConfig,
    DigestColumnsDefaults,
    FontConfig,
    HeaderConfig,
)


# ----------------------------
# Helpers: минимальный ctx
# ----------------------------


def make_min_ctx(tmp_path: Path) -> RuntimeContext:
    # Берём дефолтные колонки из реестра
    columns = tuple(
        DigestColumnsDefaults.BASE_BY_KEY[k] for k in DigestColumnsDefaults.ORDER
    )

    excel = ExcelConfig()
    excel.columns = columns
    excel.excel_path = tmp_path / "digest.xlsx"

    # header (bold=True по умолчанию), но оставим явно
    excel.header = HeaderConfig(font=FontConfig(bold=True))

    app = SimpleNamespace(excel=excel)
    return RuntimeContext(app=app)


def make_descr(task: str = "ABC-1", component: str = "Q_001") -> DescriptionOfNewTask:
    return DescriptionOfNewTask(
        task=task,
        first_solution="NEW",
        components=[component],
        description="desc",
        what_has_changed="what",
        how_it_changed="how",
    )


# ----------------------------
# 1) controller.py
# ----------------------------


def test_controller_orchestrates_services_in_order(tmp_path: Path) -> None:
    calls: list[tuple[str, Any]] = []

    class CtxSvc:
        def run(self):
            calls.append(("get_context.run", None))
            return make_min_ctx(tmp_path)

    class DescSvc:
        def run(self, *, ctx):
            calls.append(("get_description_of_new_tasks.run", ctx))
            return [
                make_descr(task="ABC-1", component="Q_001"),
                make_descr(task="ABC-2", component="Q_002"),
            ]

    class GroupSvc:
        def run(self, *, descriptions):
            calls.append(("make_grouped_descriptions.run", descriptions))
            # для простоты пусть возвращает то же самое
            return descriptions

    class ReportSvc:
        def run(self, *, ctx, descriptions):
            calls.append(("output_report.run", (ctx, descriptions)))

    controller = DigestController(
        context=CtxSvc(),
        get_description_of_new_tasks=DescSvc(),
        make_grouped_descriptions=GroupSvc(),
        output_report=ReportSvc(),
    )

    controller.run()

    # Проверяем порядок и “проброс” данных между сервисами
    assert calls[0][0] == "get_context.run"
    assert calls[1][0] == "get_description_of_new_tasks.run"
    assert calls[2][0] == "make_grouped_descriptions.run"
    assert calls[3][0] == "output_report.run"

    runtime_ctx = calls[1][1]
    assert isinstance(runtime_ctx, RuntimeContext)

    passed_desc = calls[2][1]
    assert isinstance(passed_desc, list)
    assert {d.task for d in passed_desc} == {"ABC-1", "ABC-2"}

    ctx_passed_to_report, desc_passed_to_report = calls[3][1]
    assert ctx_passed_to_report is runtime_ctx
    assert desc_passed_to_report is passed_desc


# ----------------------------
# 2) main.py
# ----------------------------


@pytest.mark.parametrize(
    "exc_type, expected_substring",
    [
        ("ConfigLoadError", "Ошибка при загрузке параметров"),
        ("ConfigError", "Ошибка в параметрах"),
        ("PermissionError", "Excel файл открыт. Закройте его"),
        ("OSError", "Ошибка ввода-вывода"),
        ("NewDirError", ""),
        ("Exception", "Неизвестная ошибка"),
    ],
)
def test_main_shows_error_messages(
        monkeypatch, exc_type: str, expected_substring: str
) -> None:
    import DIGEST_APP.main as digest_main

    # Подменяем show_error (патчить надо место использования: DIGEST_APP.APP.message.show_error,
    # потому что main импортирует show_error внутри функции main()).
    messages: list[str] = []

    def fake_show_error(msg: str) -> None:
        messages.append(msg)

    monkeypatch.setattr("DIGEST_APP.APP.message.show_error", fake_show_error)

    # Подменяем DigestController так, чтобы run() бросал нужную ошибку
    from GENERAL.errors import ConfigLoadError, ConfigError, NewDirError

    exc_map = {
        "ConfigLoadError": ConfigLoadError("x"),
        "ConfigError": ConfigError("Ошибка в параметрах"),
        "PermissionError": PermissionError("perm"),
        "OSError": OSError("io"),
        "NewDirError": NewDirError("NEW missing"),
        "Exception": RuntimeError("boom"),
    }
    to_raise = exc_map[exc_type]

    class FakeController:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            raise to_raise

    monkeypatch.setattr("DIGEST_APP.APP.controller.DigestController", FakeController)

    digest_main.main()

    assert len(messages) == 1
    if expected_substring:
        assert expected_substring in messages[0]


# ----------------------------
# 3) output_report.py
# ----------------------------


def test_output_report_open_file_returns_false_for_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_file.xlsx"
    assert OutputReport.open_file(missing) is False


def test_output_report_warns_if_open_file_raises(tmp_path: Path, monkeypatch) -> None:
    ctx = make_min_ctx(tmp_path)
    descr = [make_descr()]

    warnings: list[str] = []

    def fake_show_warning(msg: str) -> None:
        warnings.append(msg)

    # патчим show_warning в модуле output_report (там он импортирован как имя)
    monkeypatch.setattr(
        "DIGEST_APP.APP.SERVICES.output_report.show_warning",
        fake_show_warning,
    )

    # заставим open_file бросить, чтобы отработал except и show_warning()
    def boom(_path: str | Path) -> bool:
        raise OSError("cannot open")

    monkeypatch.setattr(
        OutputReport,
        "open_file",
        staticmethod(boom),
    )

    OutputReport().run(ctx=ctx, descriptions=descr)

    assert len(warnings) == 1
    assert "Файл сформирован и находится по пути" in warnings[0]
    assert "cannot open" in warnings[0]
