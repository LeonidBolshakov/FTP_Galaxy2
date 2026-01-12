from pathlib import Path, PurePosixPath
import hashlib

from SRC.SYNC_APP.APP.dto import (
    SnapshotInput,
    FileSnapshot,
    ModeSnapshot,
    DownloadDirFtpInput,
    RepositorySnapshot,
    ConfigError,
)


class SnapshotService:
    def local(self, data: SnapshotInput) -> RepositorySnapshot:
        local_dir = data.context.app.local_dir
        try:
            local_dir_iter = Path(local_dir).iterdir()
        except OSError as e:
            raise ConfigError(
                f"Неправильно задан параметр local_dir={local_dir!r}\n{e}"
            ) from e

        files: dict[str, FileSnapshot] = {}
        for file in local_dir_iter:
            if not file.is_file():
                continue
            if data.only_for is not None and file.name not in data.only_for:
                continue

            st = file.stat()
            files[file.name] = FileSnapshot(
                name=file.name,
                size=st.st_size,
                md5_hash=(
                    self._md5sum(file) if data.mode == ModeSnapshot.FULL_MODE else None
                ),
            )
        return RepositorySnapshot(files=files)

    def remote(self, data: SnapshotInput) -> RepositorySnapshot:
        if data.ftp is None:
            raise RuntimeError(
                "SnapshotService.remote. Должен быть передан параметр ftp"
            )

        items = data.ftp.download_dir(
            DownloadDirFtpInput(hash_mode=data.mode, only_for=data.only_for)
        )

        files = {
            PurePosixPath(item.remote_name).name: FileSnapshot(
                name=item.remote_name,
                size=item.size,
                md5_hash=item.md5_hash,
            )
            for item in items
        }

        return RepositorySnapshot(files=files)

    def _md5sum(self, path: Path, chunk_size: int = 1024 * 1024) -> str:
        h = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
        return h.hexdigest()
