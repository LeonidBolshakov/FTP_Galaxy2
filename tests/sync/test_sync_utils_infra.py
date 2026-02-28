from pathlib import Path

import pytest

from SYNC_APP.INFRA import utils
from GENERAL.errors import LocalFileAccessError, ConfigError


def test_name_file_to_name_component():
    cases = {
        "foo_12.zip": "foo.zip",
        "bar.tar.gz": "bar.tar.gz",
        "abc_007.txt": "abc.txt",
        "no_suffix.txt": "no_suffix.txt",
    }
    for inp, expected in cases.items():
        assert utils.name_file_to_name_component(inp) == expected


def test_safe_mkdir_creates_dir(tmp_path):
    d = tmp_path / "nested" / "dir"
    assert not d.exists()
    utils.safe_mkdir(d)
    assert d.exists() and d.is_dir()


def test_clean_dir_removes_files(tmp_path):
    # Создаём каталог с файлами
    d = tmp_path / "data"
    utils.safe_mkdir(d)
    file1 = d / "a.txt"
    file2 = d / "b.txt"
    file1.write_text("x")
    file2.write_text("y")
    utils.clean_dir(d)
    # Каталог должен существовать и быть пустым
    assert d.exists()
    assert list(d.iterdir()) == []


def test_clean_dir_raises_on_subdirectory(tmp_path):
    d = tmp_path / "data"
    utils.safe_mkdir(d)
    sub = d / "subdir"
    utils.safe_mkdir(sub)
    with pytest.raises(LocalFileAccessError):
        utils.clean_dir(d)


def test_fs_call_wraps_errors(tmp_path):
    # Создаём путь и функцию, которая вызывает OSError
    path = tmp_path / "dummy"

    def raise_oserror():
        raise OSError("bad stuff")

    with pytest.raises(LocalFileAccessError):
        utils.fs_call(path, "action", raise_oserror)


def test_sure_same_drive_detects_different_drives():
    """
    Убедитесь, что sure_same_drive выбрасывает ConfigError, если буквы дисков различаются.
    Используйте PureWindowsPath для эмуляции поведения Windows на любой платформе.
    """
    from pathlib import PureWindowsPath

    p1 = PureWindowsPath("C:/foo")
    p2 = PureWindowsPath("D:/bar")
    with pytest.raises(ConfigError):
        utils.sure_same_drive(p1, p2)


def test_default_log_and_date_file_path(monkeypatch):
    # default_log_dir должен возвращать путь внутри user_log_dir
    log_dir = utils.default_log_dir()
    assert isinstance(log_dir, Path)
    # date_file_path должен быть равен log_dir / 'date_file'
    date_path = utils.date_file_path()
    assert date_path == log_dir / "date_file"
