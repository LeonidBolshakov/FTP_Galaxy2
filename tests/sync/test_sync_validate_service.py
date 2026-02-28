import pytest

from SYNC_APP.APP.SERVICES.validate_service import ValidateService
from SYNC_APP.APP.dto import (
    DiffPlan,
    FileSnapshot,
    RepositorySnapshot,
    ValidateInput,
)
from SYNC_APP.APP.types import StatusReport, ModeDiffPlan
from types import SimpleNamespace
from SYNC_APP.APP.dto import RuntimeContext


def _ctx(tmp_path):
    """
    Создаёт минимальный RuntimeContext для тестов.

    ValidateService не зависит от конкретных полей SyncConfig во время выполнения;
    ему нужен лишь объект контекста. Мы создаём простой SimpleNamespace вместо
    строгого SyncConfig, чтобы избежать проблем с неизменяемыми свойствами.
    """
    dummy_cfg = SimpleNamespace(
        # Provide just enough attributes to satisfy other potential uses
        local_dir=tmp_path,
        ftp_host="ftp.galaktika.ru",
        ftp_root="/",
        ftp_timeout_sec=1,
        ftp_username="anonymous",
        date_file=tmp_path / "date_file",
    )
    return RuntimeContext(
        app=dummy_cfg, once_per_day=False, mode_stop_list=ModeDiffPlan.NOT_USE_STOP_LIST
    )


def test_compare_undownloaded_files():
    svc = ValidateService()
    plan_set = {"a", "b"}
    new_dir_set = {"b"}
    res = svc.compare_undownloaded_files(plan_set, new_dir_set)
    assert len(res) == 1
    assert res[0].name == "a"
    assert res[0].status is StatusReport.ERROR


def test_compare_unnecessary_files():
    svc = ValidateService()
    plan_set = {"a"}
    new_dir_set = {"a", "extra"}
    res = svc.compare_unnecessary_files(plan_set, new_dir_set)
    assert len(res) == 1
    assert res[0].name == "extra"
    assert res[0].status is StatusReport.FATAL


def test_check_size():
    svc = ValidateService()
    fs1 = FileSnapshot("file", 10, None)
    fs2 = FileSnapshot("file", 20, None)
    item = svc.check_size(fs1, fs2, "file")
    assert item is not None
    assert "10" in item.comment
    fs3 = FileSnapshot("file", 20, None)
    assert svc.check_size(fs2, fs3, "file") is None


def test_check_md5_hash_missing_and_mismatch():
    svc = ValidateService()
    local = FileSnapshot("f", 0, None)
    remote = FileSnapshot("f", 0, "abc")
    item = svc.check_md5_hash(local, remote, "f")
    assert item is not None
    assert "отсутствует".lower() in item.comment.lower()
    # mismatch
    local2 = FileSnapshot("f", 0, "a")
    remote2 = FileSnapshot("f", 0, "B")
    item2 = svc.check_md5_hash(local2, remote2, "f")
    assert item2 is not None
    assert "не совпадают" in item2.comment
    # match
    local3 = FileSnapshot("f", 0, "abc")
    remote3 = FileSnapshot("f", 0, "ABC")
    assert svc.check_md5_hash(local3, remote3, "f") is None


def test_compare_common_files_size_and_hash_missing_snapshot():
    svc = ValidateService()
    plan_set = {"file"}
    new_dir_set = {"file"}
    local_snap = RepositorySnapshot(files={})
    remote_snap = RepositorySnapshot(files={})
    with pytest.raises(RuntimeError):
        svc.compare_common_files_size_and_hash(
            plan_set, new_dir_set, local_snap, remote_snap
        )


def test_compare_common_files_size_and_hash_ok():
    svc = ValidateService()
    plan_set = {"file"}
    new_dir_set = {"file"}
    local_snap = RepositorySnapshot(files={"file": FileSnapshot("file", 1, "abc")})
    remote_snap = RepositorySnapshot(files={"file": FileSnapshot("file", 1, "ABC")})
    items = svc.compare_common_files_size_and_hash(
        plan_set, new_dir_set, local_snap, remote_snap
    )
    # md5 match should yield no items
    assert items == []


def test_run_returns_expected(tmp_path):
    svc = ValidateService()
    ctx = _ctx(tmp_path)
    # План включает два файла для загрузки
    plan = DiffPlan(
        to_delete=[],
        to_download=[FileSnapshot("f1", 1, "abc"), FileSnapshot("f2", 2, "def")],
    )
    # Создаём new_dir, в котором есть только f1; файл f2 отсутствует
    new_dir = tmp_path / "NEW"
    new_dir.mkdir()
    (new_dir / "f1").write_text("x")
    # Снимки
    local_snap = RepositorySnapshot(
        files={
            "f1": FileSnapshot("f1", 1, "abc"),
            # f2 отсутствует в локальном снимке
        }
    )
    remote_snap = RepositorySnapshot(
        files={
            "f1": FileSnapshot("f1", 1, "abc"),
            "f2": FileSnapshot("f2", 2, "def"),
        }
    )
    vi = ValidateInput(
        context=ctx,
        plan=plan,
        new_dir=new_dir,
        local_snap=local_snap,
        remote_snap=remote_snap,
    )
    ok, report = svc.run(vi)
    # Один файл отсутствует -> отчёт об ошибке должен содержать один элемент
    assert ok is False
    names = [r.name for r in report]
    assert "f2" in names
