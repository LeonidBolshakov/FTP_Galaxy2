import pytest
from pathlib import Path

from DIGEST_APP.APP.SERVICES.get_description_of_new_tasks import (
    GetDescriptionOfNewTasks,
)
from DIGEST_APP.APP.dto import RuntimeContext
from GENERAL.errors import NewDirError


def test_missing_new_dir_returns_empty_list(digest_ctx: RuntimeContext):
    svc = GetDescriptionOfNewTasks()
    assert svc.run(digest_ctx) == []


def test_empty_new_dir_returns_empty_list(digest_ctx_with_new: RuntimeContext):
    svc = GetDescriptionOfNewTasks()
    assert svc.run(digest_ctx_with_new) == []


def test_new_dir_is_file_raises(digest_ctx, tmp_path: Path):
    file_path = tmp_path / "NEW"
    file_path.write_text("q")
    digest_ctx.app.new_dir = file_path

    svc = GetDescriptionOfNewTasks()
    with pytest.raises(NewDirError):
        assert svc.run(digest_ctx) == []


def test_parse_single_file(digest_ctx):
    text = """
ИНФОРМАЦИЯ ПО ОБНОВЛЕНИЮ КОМПОНЕНТА
* ОБНОВЛЕНИЕ: ATLPICTURE_OCX_55150
* НАЗНАЧЕНИЕ: Общее
* ПРОДУКТ и ВЕРСИЯ: Atlantis 5.5
* РЕЛИЗ: 20.03.2012 : 
* СИСТЕМНАЯ ПЛАТФОРМА: *, 
* КОМПОНЕНТ: ATLPICTURE
* ТИП: OCX
* ВЕРСИЯ: 5.5.15.0
# ИНСТРУКЦИЯ ПО УСТАНОВКЕ: 
1. Данное обновление устанавливается с помощью последней версии Менеджера
   обновлений, доступной на 
FTP://ftp.galaktika.ru/pub/support/galaktika/bug_fix/GAL910/PATCHMANAGER/
2. Остановить работу пользователей с системой Галактика ERP
   и с утилитами администратора комплекса Support.
   В трехуровневой архитектуре остановить работу сервера приложений.
3. Далее провести процедуру согласно описанию Менеджера обновлений.

* * *
# ЗАДАЧА В JIRA: ABC-2
* ПЕРВОЕ РЕШЕНИЕ: NEW
# КРАТКОЕ ОПИСАНИЕ: hello
* ЧТО ИЗМЕНЕНО: changes
# КАК ИЗМЕНЕНО: details
    """
    new_dir = digest_ctx.app.new_dir
    new_dir.mkdir(parents=True)

    file = new_dir / "ABC_9101_1954_003.txt"
    file.write_text(text, encoding="cp1251")
    digest_ctx.app.new_dir = new_dir
    src = GetDescriptionOfNewTasks()
    descriptions = src.run(digest_ctx)
    assert len(descriptions) == 1
    item = descriptions[0]
    assert item.task == "ABC-2"
    assert item.first_solution == "NEW"
    assert item.description == "hello"
    assert item.what_has_changed == "changes"
    assert item.how_it_changed == "details"
    assert item.components == ["ABC_9101_1954_003"]


def test_parse_two_file(digest_ctx):
    text_1 = """
ИНФОРМАЦИЯ ПО ОБНОВЛЕНИЮ КОМПОНЕНТА
* ОБНОВЛЕНИЕ: ATLPICTURE_OCX_55150
* НАЗНАЧЕНИЕ: Общее
* ПРОДУКТ и ВЕРСИЯ: Atlantis 5.5
* РЕЛИЗ: 20.03.2012 : 
* СИСТЕМНАЯ ПЛАТФОРМА: *, 
* КОМПОНЕНТ: ATLPICTURE
* ТИП: OCX
* ВЕРСИЯ: 5.5.15.0
# ИНСТРУКЦИЯ ПО УСТАНОВКЕ: 
1. Данное обновление устанавливается с помощью последней версии Менеджера
   обновлений, доступной на 
FTP://ftp.galaktika.ru/pub/support/galaktika/bug_fix/GAL910/PATCHMANAGER/
2. Остановить работу пользователей с системой Галактика ERP
   и с утилитами администратора комплекса Support.
   В трехуровневой архитектуре остановить работу сервера приложений.
3. Далее провести процедуру согласно описанию Менеджера обновлений.

* * *
# ЗАДАЧА В JIRA: ABC-2
* ПЕРВОЕ РЕШЕНИЕ: NEW
# КРАТКОЕ ОПИСАНИЕ: hello
* ЧТО ИЗМЕНЕНО: changes
# КАК ИЗМЕНЕНО: details
    """
    text_2 = """
3. Далее провести процедуру согласно описанию Менеджера обновлений.
* * *
* ПЕРВОЕ РЕШЕНИЕ: NEW
# ЗАДАЧА В JIRA: ABC-10
* ПЕРВОЕ РЕШЕНИЕ: NEW
# КРАТКОЕ ОПИСАНИЕ: tram
* ЧТО ИЗМЕНЕНО: all
# КАК ИЗМЕНЕНО: gut
"""

    new_dir = digest_ctx.app.new_dir
    new_dir.mkdir(parents=True)

    file_1 = new_dir / "Q_001.txt"
    file_1.write_text(text_1, encoding="cp1251")
    file_2 = new_dir / "Q_003.txt"
    file_2.write_text(text_2, encoding="cp1251")

    digest_ctx.app.new_dir = new_dir
    src = GetDescriptionOfNewTasks()
    descriptions = src.run(digest_ctx)

    assert len(descriptions) == 2

    item = descriptions[0]
    assert item.task == "ABC-2"
    assert item.first_solution == "NEW"
    assert item.description == "hello"
    assert item.what_has_changed == "changes"
    assert item.how_it_changed == "details"
    assert item.components == ["Q_001"]

    item = descriptions[1]
    assert item.task == "ABC-10"
    assert item.first_solution == "NEW"
    assert item.description == "tram"
    assert item.what_has_changed == "all"
    assert item.how_it_changed == "gut"
    assert item.components == ["Q_003"]
