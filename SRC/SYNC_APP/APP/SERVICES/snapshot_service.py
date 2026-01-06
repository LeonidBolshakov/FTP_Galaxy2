from pathlib import Path
import hashlib

from SRC.SYNC_APP.ADAPTERS.ftp import Ftp

from SRC.SYNC_APP.APP.dto import (
    SnapshotInput,
    RepositorySnapshot,
    FileSnapshot,
    FileSnapshot,
    FTPInput,
    DownloadFileError,
    RepositorySnapshotError,
    ModeSnapShop,
    DownloadDirFtpInput,
    RepositorySnapshot,
)


class SnapShotService:
    def local(self, data: SnapshotInput) -> RepositorySnapshot:
        local_dir = data.context.app.local_dir

        files = dict()
        for file in local_dir.iterdir():
            if file.is_file():
                files[file.name] = FileSnapshot(
                    file.name,
                    file.stat().st_size,
                    (
                        self._md5sum(file)
                        if data.mode == ModeSnapShop.FULL_MODE
                        else None
                    ),
                )
        return RepositorySnapshot(files=files)

    def remote(self, data: SnapshotInput) -> RepositorySnapshot:
        ftp = Ftp(FTPInput(data.context, data.ftp))
        ftp.connect()
        try:
            items = ftp.download_dir(
                DownloadDirFtpInput(with_md5=data.mode, only_for=data.only_for)
            )
        except DownloadFileError as e:
            raise RepositorySnapshotError(
                f"Не удалось получить список файлов с удалённого сервера: {e}"
            ) from e

        files = {
            items.remote_full: FileSnapshot(
                name=items.remote_full,
                size=items.size,
                md5_hash=items.md5_hash,
            )
            for items in items
        }

        return RepositorySnapshot(files=files)

    def _md5sum(self, path: Path, chunk_size=1024 * 1024) -> str:
        h = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
        return h.hexdigest()
