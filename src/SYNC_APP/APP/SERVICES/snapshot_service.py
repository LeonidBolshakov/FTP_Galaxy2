"""
snapshot_service.py

Сервис построения «снимка» (snapshot) репозитория: локального каталога и удалённого FTP-каталога.

Задача сервиса:
- собрать список файлов (name/size и опционально md5) из локальной директории;
- запросить аналогичный список с удалённой стороны через ftp-клиент;
- вернуть результат в виде RepositorySnapshot.

Примечание по режимам:
- ModeSnapshot.FULL_MODE: вычисляется md5 каждого локального файла;
- иначе md5 не вычисляется (md5_hash=None).
"""

from pathlib import Path
from typing import Set
import hashlib

from SYNC_APP.APP.dto import (
    SnapshotInput,
    FileSnapshot,
    ModeSnapshot,
    DownloadDirFtpInput,
    RepositorySnapshot,
)
from GENERAL.errors import ConfigError, DownloadDirError

# Размер блока чтения при вычислении md5 (1 MiB)
CHUNK_SIZE = 1024 * 1024


class SnapshotService:
    """Сервис получения снапшотов (списков файлов) для локального и удалённого репозитория."""

    def local(self, data: SnapshotInput) -> RepositorySnapshot:
        """
        Построить снапшот локальной директории.

        Собирает файлы верхнего уровня директории `data.local_dir` (без рекурсии),
        фильтрует по `data.only_for` (если задан), и для каждого файла получает:
        - размер (st_size)
        - md5 (только в режиме ModeSnapshot.FULL_MODE)

        Args:
            data: SnapshotInput, где обязательно задан `local_dir`.

        Returns:
            RepositorySnapshot: словарь файлов по имени (files[name] -> FileSnapshot).

        Raises:
            RuntimeError: если `data.local_dir` не задан (это ошибка контракта вызова).
            ConfigError: если директория не может быть открыта/прочитана (нет доступа, не существует и т.п.).
            DownloadDirError: если не удалось прочитать атрибуты файла или вычислить хэш.
        """
        if data.local_dir is None:
            raise RuntimeError("SnapshotService.local Параметр local_dir обязателен")
        local_path = Path(data.local_dir)

        # Пробуем получить итератор по элементам каталога (ошибки доступа/ФС считаем конфигурационными)
        try:
            local_dir_iter = local_path.iterdir()
        except OSError as e:
            raise ConfigError(
                f"{self._where('local_snap')}: Не удалось открыть file_full_path={local_path!r}.\n"
                f"Проверьте параметр local_path и доступность директории "
                f"(её могли удалить/переместить или на неё нет прав).\n"
                f"{e}"
            ) from e

        files: dict[str, FileSnapshot] = {}
        for file in local_dir_iter:
            # Берём только обычные файлы; директории/ссылки/прочее пропускаем
            if not file.is_file():
                continue
            # Фильтр "скачивать/учитывать только имена из only_for"
            if not self._allowed(file.name, data.only_for):
                continue

            # Читаем метаданные файла (размер и т.п.)
            try:
                st = file.stat()
            except OSError as e:
                raise DownloadDirError(
                    f"{self._where('local_snap')}: Ошибка при чтении атрибутов файла {file!s}\n{e}"
                ) from e

            # В FULL_MODE считаем md5, для синхронизации с FTP сервером
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
        """
        Построить снапшот удалённого каталога через FTP-клиент.

        Использует `data.ftp.download_dir(...)` и возвращает RepositorySnapshot
        на основе `items.files`, полученных от FTP слоя.

        Args:
            data: SnapshotInput, где обязательно задан `ftp`.

        Returns:
            RepositorySnapshot: словарь файлов по имени (files[name] -> FileSnapshot).

        Raises:
            RuntimeError: если `data.ftp` не задан (это ошибка контракта вызова).
            Исключения, которые может выбросить FTP-слой (зависят от реализации data.ftp).
        """
        if data.ftp is None:
            raise RuntimeError(
                f"{self._where('remote_snap')}: должен быть передан параметр ftp"
            )

        items = data.ftp.download_dir(
            DownloadDirFtpInput(hash_mode=data.mode, only_for=data.only_for)
        )

        return RepositorySnapshot(files=items.files)

    @staticmethod
    def _allowed(name: str, only_for: Set[str] | None) -> bool:
        """
        Проверка фильтра по списку разрешённых имён.

        Args:
            name: имя файла.
            only_for: коллекция имён, которые разрешены, либо None.

        Returns:
            True, если фильтр не задан (only_for is None) или имя содержится в only_for.
        """
        return only_for is None or name in only_for

    def _where(self, method: str) -> str:
        """
        Служебный метод для формирования префикса в сообщениях об ошибках.

        Args:
            method: логическое имя “места” (например, 'local_snap').

        Returns:
            Строка вида '<ClassName>.<method>'.
        """
        return f"{type(self).__name__}.{method}"

    def _md5_hash(self, path: Path) -> str:
        """
        Вычислить md5-хэш файла по пути `path`.

        Читает файл блоками размера CHUNK_SIZE.

        Args:
            path: путь к локальному файлу.

        Returns:
            hex-строка md5.

        Raises:
            DownloadDirError: если файл не удалось открыть/прочитать во время хэширования.
        """
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
