from SYNC_APP.APP.dto import (
    RuntimeContext,
    FileSnapshot,
    DownloadDirFtpInput,
    SnapshotInput,
)
from SYNC_APP.APP.types import ModeDiffPlan, ModeSnapshot
from SYNC_APP.CONFIG.config import SyncConfig


def _make_runtime_context(tmp_path):
    # Используем допустимый ftp_host, чтобы пройти валидацию SyncConfig (см. CONFIG.config)
    cfg = SyncConfig(
        local_dir=tmp_path,
        ftp_host="ftp.galaktika.ru",
        ftp_root="/",
        ftp_timeout_sec=1,
        ftp_username="anonymous",
    )
    return RuntimeContext(
        app=cfg, once_per_day=False, mode_stop_list=ModeDiffPlan.NOT_USE_STOP_LIST
    )


def test_file_snapshot_equality_and_hash():
    a = FileSnapshot(name=" file.txt ", size=10, md5_hash="abc")
    b = FileSnapshot(name="file.txt", size=100, md5_hash="def")
    # сравнение игнорирует размер и хэш и обрезает пробелы в имени
    assert a == b
    assert hash(a) == hash(b)


def test_download_dir_ftp_input_repr():
    d1 = DownloadDirFtpInput()
    repr1 = repr(d1)
    # Когда only_for равно None, в строковом представлении должно быть «None»
    assert "None" in repr1
    d2 = DownloadDirFtpInput(only_for={"a", "b", "c"})
    repr2 = repr(d2)
    assert "3 files" in repr2


def test_snapshot_input_defaults(tmp_path):
    ctx = _make_runtime_context(tmp_path)
    # локальный снимок без указания необязательных полей
    si = SnapshotInput(context=ctx, mode=ModeSnapshot.LITE_MODE, local_dir=tmp_path)
    assert si.ftp is None

    # удалённый снимок с заглушкой ftp
    class DummyFtp:
        pass

    ftp = DummyFtp()
    si2 = SnapshotInput(context=ctx, mode=ModeSnapshot.LITE_MODE, ftp=ftp)
    assert si2.ftp is ftp
