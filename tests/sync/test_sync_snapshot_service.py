from SYNC_APP.APP.SERVICES.snapshot_service import SnapshotService
from SYNC_APP.APP.dto import SnapshotInput, RepositorySnapshot, FileSnapshot
from SYNC_APP.APP.types import ModeSnapshot, ModeDiffPlan
from SYNC_APP.CONFIG.config import SyncConfig
from SYNC_APP.APP.dto import RuntimeContext


def _ctx(tmp_path):
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


def test_allowed_function():
    svc = SnapshotService()
    assert svc._allowed("file.txt", None) is True
    assert svc._allowed("file.txt", {"file.txt"}) is True
    assert svc._allowed("other.txt", {"file.txt"}) is False


def test_md5_hash_computation(tmp_path):
    svc = SnapshotService()
    file = tmp_path / "data.bin"
    # Создаём файл с известным содержимым
    file.write_bytes(b"abc123")
    h = svc._md5_hash(file)
    import hashlib

    assert h == hashlib.md5(b"abc123").hexdigest()


def test_local_snapshot(tmp_path):
    svc = SnapshotService()
    ctx = _ctx(tmp_path)
    # Создаём файлы
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("A")
    f2.write_text("BC")
    si = SnapshotInput(context=ctx, mode=ModeSnapshot.LITE_MODE, local_dir=tmp_path)
    snap = svc.local(si)
    assert isinstance(snap, RepositorySnapshot)
    assert set(snap.files.keys()) == {"a.txt", "b.txt"}
    # размеры должны соответствовать длине файлов
    assert snap.files["a.txt"].size == 1
    assert snap.files["b.txt"].size == 2
    # md5 должен быть None в режиме LITE_MODE
    assert snap.files["a.txt"].md5_hash is None


def test_remote_snapshot(tmp_path):
    svc = SnapshotService()
    ctx = _ctx(tmp_path)

    class DummyFtp:
        def __init__(self):
            self.called = False

        def download_dir(self, di):
            self.called = True
            return RepositorySnapshot(files={"x.txt": FileSnapshot("x.txt", 1, None)})

    ftp = DummyFtp()
    si = SnapshotInput(context=ctx, mode=ModeSnapshot.LITE_MODE, ftp=ftp)
    snap = svc.remote(si)
    assert isinstance(snap, RepositorySnapshot)
    assert ftp.called
    assert "x.txt" in snap.files
