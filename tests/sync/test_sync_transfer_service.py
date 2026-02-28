import pytest

from SYNC_APP.APP.SERVICES.transfer_service import TransferService, NewDirAction
from SYNC_APP.APP.dto import FileSnapshot
from SYNC_APP.APP.types import StatusReport


def test_index_snapshots_by_name():
    svc = TransferService(new_dir_selector=lambda _: NewDirAction.CONTINUE)
    snaps = [FileSnapshot("a", 1, None), FileSnapshot("b", 2, None)]
    indexed = svc._index_snapshots_by_name(snaps)
    assert indexed["a"].size == 1
    assert indexed["b"].size == 2


def test_make_sure_is_file_appends_fatal(tmp_path):
    # Передаём путь к каталогу внутри tmp_path
    svc = TransferService(new_dir_selector=lambda _: NewDirAction.CONTINUE)
    # Сбрасываем список отчётов
    svc.report = []
    subdir = tmp_path / "sub"
    subdir.mkdir()
    svc._make_sure_is_file(subdir)
    assert svc.report
    assert svc.report[0].status is StatusReport.FATAL


def test_unlink_zero_file(tmp_path):
    svc = TransferService(new_dir_selector=lambda _: NewDirAction.CONTINUE)
    svc.report = []
    zero = tmp_path / "zero.txt"
    zero.write_text("")
    # Убеждаемся, что файл существует
    assert zero.exists()
    svc._unlink_zero_file(zero)
    # Файл должен быть удалён
    assert not zero.exists()


def test_ensure_new_and_old_dirs_ready_handles_stop(tmp_path):
    # Создаём каталоги
    new_dir = tmp_path / "NEW"
    old_dir = tmp_path / "OLD"
    new_dir.mkdir()
    old_dir.mkdir()
    # Помещаем файл в new_dir, чтобы вызвать запрос
    (new_dir / "file.txt").write_text("abc")
    # new_dir_selector возвращает STOP
    svc = TransferService(new_dir_selector=lambda _: NewDirAction.STOP)
    svc.report = []
    res = svc._ensure_new_and_old_dirs_are_ready(new_dir=new_dir, old_dir=old_dir)
    assert res is False
    # Отчёт должен содержать одну запись со статусом ERROR
    assert svc.report
    assert svc.report[0].status is StatusReport.ERROR


def test_ensure_new_and_old_dirs_ready_handles_restart(tmp_path):
    new_dir = tmp_path / "NEW"
    old_dir = tmp_path / "OLD"
    new_dir.mkdir()
    old_dir.mkdir()
    (new_dir / "file.txt").write_text("abc")
    (old_dir / "old_file.txt").write_text("abc")
    # new_dir_selector возвращает RESTART, поэтому каталоги очищаются
    svc = TransferService(new_dir_selector=lambda _: NewDirAction.RESTART)
    svc.report = []
    res = svc._ensure_new_and_old_dirs_are_ready(new_dir=new_dir, old_dir=old_dir)
    assert res is True
    # new_dir и old_dir должны быть пустыми после рестарта
    assert list(new_dir.iterdir()) == []
    assert list(old_dir.iterdir()) == []


def test_get_local_file_size(tmp_path):
    svc = TransferService(new_dir_selector=lambda _: NewDirAction.CONTINUE)
    file = tmp_path / "f.txt"
    file.write_text("abc")
    # Должен вернуть размер 3
    assert svc.get_local_file_size(file) == 3
    # Несуществующий файл должен приводить к LocalFileAccessError согласно текущей реализации
    from GENERAL.errors import LocalFileAccessError

    with pytest.raises(LocalFileAccessError):
        svc.get_local_file_size(tmp_path / "missing")
