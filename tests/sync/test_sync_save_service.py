"""
Тесты для `save_service` на русском языке.

Эти тесты покрывают функции в сервисе сохранения: проверку типов файлов,
получение параметров из контекста, очистку директории OLD с различными действиями,
а также основной сценарий commit_keep_new_old_dirs.
"""

from pathlib import Path
import pytest

from SYNC_APP.APP.SERVICES.save_service import SaveService, OldDirAction
from SYNC_APP.APP.dto import FileSnapshot, SaveInput
from GENERAL.errors import LocalFileAccessError, ConfigError, UserAbend

from types import SimpleNamespace


def test_enshure_is_file_raises(tmp_path) -> None:
    """
    Убедимся, что попытка передать каталог вместо файла вызывает LocalFileAccessError.
    """
    svc = SaveService(old_dir_selector=lambda _: OldDirAction.CONTINUE)
    dir_path = tmp_path / "dir"
    dir_path.mkdir()
    with pytest.raises(LocalFileAccessError):
        svc._enshure_is_file(dir_path)


def test_get_parameter_returns_attr(tmp_path) -> None:
    """
    Метод `_get_parameter` должен возвращать путь из атрибута контекста
    и выбрасывать ConfigError для несуществующего параметра.
    """
    # Создаём объект app с атрибутом local_dir
    app = SimpleNamespace(local_dir=tmp_path)
    ctx = SimpleNamespace(app=app)
    svc = SaveService(old_dir_selector=lambda _: OldDirAction.CONTINUE)
    # Должен вернуть путь local_dir
    assert svc._get_parameter("local_dir", SaveInput(context=ctx, delete=[])) == Path(
        tmp_path
    )
    # Неизвестный атрибут должен привести к исключению ConfigError
    with pytest.raises(ConfigError):
        svc._get_parameter("nonexistent", SaveInput(context=ctx, delete=[]))


def test_sure_empty_directory_actions(tmp_path) -> None:
    """
    Проверяем поведение sure_empty_directory в зависимости от выбора пользователя:
    DELETE/CONTINUE очищают каталог, STOP вызывает UserAbend.
    """
    # Создаём каталог old с файлом
    dir_old = tmp_path / "old"
    dir_old.mkdir()
    (dir_old / "data.txt").write_text("abc")
    # DELETE: очистка
    svc = SaveService(old_dir_selector=lambda _: OldDirAction.DELETE)
    svc.sure_empty_directory(dir_old)
    assert list(dir_old.iterdir()) == []
    # Создаём новый файл и тестируем CONTINUE (тот же эффект)
    (dir_old / "data2.txt").write_text("abc")
    svc = SaveService(old_dir_selector=lambda _: OldDirAction.CONTINUE)
    svc.sure_empty_directory(dir_old)
    assert list(dir_old.iterdir()) == []
    # Для STOP должно быть исключение UserAbend
    (dir_old / "data3.txt").write_text("abc")
    svc = SaveService(old_dir_selector=lambda _: OldDirAction.STOP)
    with pytest.raises(UserAbend):
        svc.sure_empty_directory(dir_old)


def test_commit_keep_new_old_dirs_moves_and_copies(tmp_path) -> None:
    """
    Полный сценарий: файлы из списка delete перемещаются в OLD,
    а файлы из NEW копируются в local_dir. Возвращаются отчётные записи.
    """
    # Директории
    local_dir = tmp_path / "local"
    new_dir = tmp_path / "NEW"
    old_dir = tmp_path / "OLD"
    local_dir.mkdir()
    new_dir.mkdir()
    old_dir.mkdir()
    # Подготовим файлы в local_dir, которые должны быть перемещены в OLD
    (local_dir / "old1.txt").write_text("x")
    (local_dir / "old2.txt").write_text("y")
    delete_snaps = [
        FileSnapshot(name="old1.txt", size=1, md5_hash=None),
        FileSnapshot(name="old2.txt", size=1, md5_hash=None),
    ]
    # Подготовим файл в new_dir, который будет скопирован в local_dir
    (new_dir / "newfile.bin").write_text("data")
    # Контекст с нужными атрибутами
    app = SimpleNamespace(local_dir=local_dir, new_dir=new_dir, old_dir=old_dir)
    ctx = SimpleNamespace(app=app)
    svc = SaveService(old_dir_selector=lambda _: OldDirAction.CONTINUE)
    report = svc.commit_keep_new_old_dirs(SaveInput(context=ctx, delete=delete_snaps))
    # Файлы из delete перемещены
    assert not (local_dir / "old1.txt").exists()
    assert not (local_dir / "old2.txt").exists()
    assert (old_dir / "old1.txt").exists()
    assert (old_dir / "old2.txt").exists()
    # Файлы из NEW скопированы
    assert (local_dir / "newfile.bin").exists()
    # Отчёт содержит две строки (для move и copy)
    assert len(report) == 2
    assert report[0].status.name == "INFO"
    assert "перемещено" in report[0].comment
    assert report[1].status.name == "INFO"
    assert "перемещено" in report[1].comment or "перемещено" in report[1].comment


def test_copy_file_to_temp_creates_copy(tmp_path) -> None:
    """
    Проверяем, что _copy_file_to_temp создаёт копию файла в той же папке.
    """
    svc = SaveService(old_dir_selector=lambda _: OldDirAction.CONTINUE)
    src = tmp_path / "source.txt"
    src.write_text("hello")
    temp_path = svc._copy_file_to_temp(src)
    # Копия должна существовать и содержать те же данные
    assert temp_path.exists()
    assert temp_path.read_text() == "hello"
