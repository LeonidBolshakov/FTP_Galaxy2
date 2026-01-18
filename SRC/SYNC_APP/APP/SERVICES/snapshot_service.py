from pathlib import Path
import hashlib

from SRC.SYNC_APP.APP.dto import (
    SnapshotInput,
    FileSnapshot,
    ModeSnapshot,
    DownloadDirFtpInput,
    RepositorySnapshot,
    ConfigError,
    DownloadDirError,
)

CHUNK_SIZE = 1024 * 1024


class SnapshotService:
    def local(self, data: SnapshotInput) -> RepositorySnapshot:
        if data.local_dir is None:
            raise RuntimeError("SnapshotService.local Параметр local_dir обязателен")
        local_path = Path(data.local_dir)

        try:
            local_dir_iter = local_path.iterdir()
        except OSError as e:
            raise ConfigError(
                f"{self._where('local_snap')}: Не удалось открыть local_dir={local_path!r}.\n"
                f"Проверьте параметр local_dir и доступность директории "
                f"(её могли удалить/переместить или на неё нет прав).\n"
                f"{e}"
            ) from e

        files: dict[str, FileSnapshot] = {}
        for file in local_dir_iter:
            if not file.is_file():
                continue
            if not self._allowed(file.name, data.only_for):
                continue

            try:
                st = file.stat()
            except OSError as e:
                raise DownloadDirError(
                    f"{self._where('local_snap')}: Ошибка при чтении атрибутов файла {file!s} "
                    f"(local_dir={local_path!r}).\n{e}"
                ) from e

            md5_hash = (
                self._md5_hash(file) if data.mode == ModeSnapshot.FULL_MODE else None
            )

            files[file.name] = FileSnapshot(
                name=file.name,
                size=st.st_size,
                md5_hash=md5_hash,
            )
        return RepositorySnapshot(files=files)

    def remote(self, data: SnapshotInput) -> RepositorySnapshot:
        if data.ftp is None:
            raise RuntimeError(
                f"{self._where('remote_snap')}: должен быть передан параметр ftp"
            )

        items = data.ftp.download_dir(
            DownloadDirFtpInput(hash_mode=data.mode, only_for=data.only_for)
        )

        return RepositorySnapshot(files=items.files)

    @staticmethod
    def _allowed(name: str, only_for) -> bool:
        return only_for is None or name in only_for

    def _where(self, method: str) -> str:
        return f"{type(self).__name__}.{method}"

    def _md5_hash(self, path: Path) -> str:
        h = hashlib.md5()
        try:
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                    h.update(chunk)
        except OSError as e:
            raise DownloadDirError(
                f"{self._where('local_snap')}: Ошибка при чтении/хешировании локального файла {path!s}\n"
                f"{e}"
            ) from e

        return h.hexdigest()
