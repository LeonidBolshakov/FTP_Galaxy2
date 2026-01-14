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
        local_dir = data.context.app.local_dir
        local_path = Path(local_dir)

        try:
            local_dir_iter = local_path.iterdir()
        except OSError as e:
            raise ConfigError(
                f"{self._where('local')}: Не удалось открыть local_dir={local_dir!r}.\n"
                f"Проверьте параметр local_dir и доступность директории "
                f"(её могли удалить/переместить или нет прав).\n"
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
                    f"{self._where('local')}: Ошибка при чтении атрибутов файла {file!s} "
                    f"(local_dir={local_dir!r}).\n{e}"
                ) from e

            md5_hash = None
            if data.mode == ModeSnapshot.FULL_MODE:
                try:
                    md5_hash = self._md5sum(file)
                except OSError as e:
                    raise DownloadDirError(
                        f"{self._where('local')}: Ошибка при чтении/хешировании локального файла {file!s} "
                        f"(local_dir={local_dir!r}).\n{e}"
                    ) from e

            files[file.name] = FileSnapshot(
                name=file.name,
                size=st.st_size,
                md5_hash=md5_hash,
            )
        return RepositorySnapshot(files=files)

    def remote(self, data: SnapshotInput) -> RepositorySnapshot:
        if data.ftp is None:
            raise RuntimeError(
                f"{self._where('remote')}: должен быть передан параметр ftp"
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

    def _md5sum(self, path: Path) -> str:
        h = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                h.update(chunk)
        return h.hexdigest()
