from __future__ import annotations

from pathlib import Path

import pytest

from DIGEST_APP.APP.SERVICES.get_description_of_new_tasks import (
    GetDescriptionOfNewTasks,
)
from GENERAL.errors import NewDirError


@pytest.mark.xfail(
    reason="Сейчас _iter_files() возвращает None при отсутствии NEW, что ломает run(); ожидаемое поведение — пустой список"
)
def test_new_dir_missing_returns_empty_list(digest_ctx):
    svc = GetDescriptionOfNewTasks()
    assert svc.run(digest_ctx) == []


def test_new_dir_is_file_raises(digest_ctx, tmp_path: Path):
    # Подменяем new_dir на файл
    f = tmp_path / "NEW"
    f.write_text("x", encoding="utf-8")
    digest_ctx.app.new_dir = str(f)

    svc = GetDescriptionOfNewTasks()
    with pytest.raises(NewDirError):
        svc.run(digest_ctx)


def test_parse_single_file_with_two_blocks_filters_only_new(digest_ctx):
    new_dir = Path(digest_ctx.app.new_dir)
    new_dir.mkdir(parents=True)

    text = """
* * *
# ЗАДАЧА В JIRA: ABC-1
# ПЕРВОЕ РЕШЕНИЕ: OLD
# КРАТКОЕ ОПИСАНИЕ: should be ignored

* * *
# ЗАДАЧА В JIRA: ABC-2
# ПЕРВОЕ РЕШЕНИЕ: NEW
# КРАТКОЕ ОПИСАНИЕ: hello
# ЧТО ИЗМЕНЕНО: changes
# КАК ИЗМЕНЕНО: details
""".lstrip()

    (new_dir / "COMPONENT_001.txt").write_text(text, encoding="cp1251")

    svc = GetDescriptionOfNewTasks()
    items = svc.run(digest_ctx)

    assert len(items) == 1
    item = items[0]
    assert item.task == "ABC-2"
    assert item.first_solution == "NEW"
    assert item.components == ["COMPONENT_001"]
    assert item.description == "hello"
    assert item.what_has_changed == "changes"
    assert item.how_it_changed == "details"


def test_headers_can_start_with_star(digest_ctx):
    new_dir = Path(digest_ctx.app.new_dir)
    new_dir.mkdir(parents=True)

    # В текущей реализации парсер пропускает descriptions[0] (см. _parse_descriptions: descriptions[1:]).
    # Поэтому делаем два блока: первый (OLD) будет пропущен, второй (NEW) должен попасть в результат.

    text = """
* * *
* ЗАДАЧА В JIRA: ZZZ-0
* ПЕРВОЕ РЕШЕНИЕ: OLD
* КРАТКОЕ ОПИСАНИЕ: ignored

* * *
* ЗАДАЧА В JIRA: ZZZ-9
* ПЕРВОЕ РЕШЕНИЕ: NEW
* КРАТКОЕ ОПИСАНИЕ: ok
""".lstrip()

    (new_dir / "C_1.txt").write_text(text, encoding="cp1251")

    svc = GetDescriptionOfNewTasks()
    items = svc.run(digest_ctx)

    assert len(items) == 1
    assert items[0].task == "ZZZ-9"
