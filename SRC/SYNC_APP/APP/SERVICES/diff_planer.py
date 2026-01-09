from loguru import logger
import os
import posixpath
from pathlib import PurePosixPath
from typing import Mapping

from SRC.SYNC_APP.APP.dto import (
    DiffPlan,
    DiffInput,
    InvalidFile,
    FileSnapshot,
    ModeDiffPlan,
)


class DiffPlanner:
    """Строит план синхронизации локальной директории с удалённым (FTP).

    Назначение:
        — определить, какие файлы нужно удалить локально (лишние),
        — какие нужно скачать (отсутствуют локально),
        — какие присутствуют в обоих местах, но отличаются по размеру/хэшу.

    Важно:
        Сравнение производится по *имени файла* (basename), без учёта каталогов.
        Для remote-части ключи нормализуются как Path(remote_path).path.
        Это означает, что два разных remote-пути с одинаковым basename считаются конфликтом.
    """

    def run(self, data: DiffInput) -> DiffPlan:
        """Сравнивает локальные и удалённые файлы и возвращает DiffPlan.

        Алгоритм:
            1) Берёт локальные файлы как есть: `data.local.files` (dict[path -> FileSnapshot]).
            2) Преобразует удалённые файлы к словарю `basename -> FileSnapshot`.
               При обнаружении двух remote-файлов с одинаковым basename — бросает ValueError.
            3) По множествам ключей вычисляет:
               - to_delete   = local - remote
               - to_download = remote - local
               - common      = local ∩ remote
            4) Для common сравнивает пары FileSnapshot по size и md5_hash и формирует список InvalidFile.

        Args:
            data: DiffInput, содержащий два снимка: local и remote.

        Returns:
            DiffPlan:
                - to_delete: отсортированный список FileSnapshot, которые есть локально, но отсутствуют на сервере;
                - to_download: отсортированный список FileSnapshot, которые есть на сервере, но отсутствуют локально;
                - diff_files: список расхождений для файлов, присутствующих в обоих снимках.
        """
        local_files: dict[str, FileSnapshot] = data.local.files
        remote_files: dict[str, FileSnapshot] = self._remote_files_by_basename(
            data.remote.files
        )

        local_names: set[str] = self._names(local_files)
        remote_names: set[str] = self._names(remote_files)

        common_names: set[str] = self._common_names(local_names, remote_names)
        delete_names: set[str] = self._delete_names(local_names, remote_names)

        raw_download_names: set[str] = self._download_names(local_names, remote_names)
        download_names: set[str] = self._apply_stop_add_lists(data, raw_download_names)

        to_delete: list[FileSnapshot] = self._collect_snapshots(
            local_files, delete_names
        )
        to_download: list[FileSnapshot] = self._collect_snapshots(
            remote_files, download_names
        )

        diff_files: list[InvalidFile] = self._diff_common(
            common_names, local_files, remote_files
        )

        return self._build_plan(to_delete, to_download, diff_files)

    # 1) Нормализация remote: ключ -> basename
    def _remote_files_by_basename(
            self,
            remote_files: Mapping[str, FileSnapshot],
    ) -> dict[str, FileSnapshot]:
        # PurePosixPath безопаснее для FTP-путей ("/"), чем Path.
        return {PurePosixPath(p).name: snap for p, snap in remote_files.items()}

    # 2) Получение множества имён (ключей словаря)
    def _names(self, files: Mapping[str, FileSnapshot]) -> set[str]:
        return set(files)

    # 3) Операции над множествами имён
    def _common_names(self, local: set[str], remote: set[str]) -> set[str]:
        return local & remote

    def _delete_names(self, local: set[str], remote: set[str]) -> set[str]:
        return local - remote

    def _download_names(self, local: set[str], remote: set[str]) -> set[str]:
        return remote - local

    # 4) Применение stop/add списков (если включено)
    def _apply_stop_add_lists(self, data: DiffInput, download: set[str]) -> set[str]:
        if data.use_stop_add_lists != ModeDiffPlan.USE_STOP_ADD_LISTS:
            return download

        # работаем с копией, чтобы не мутировать входной set снаружи
        result = set(download)
        result -= self.apply_stop_set(data, result)
        result |= self.apply_add_set(data, result)
        return result

    # 5) Сбор FileSnapshot по именам
    def _collect_snapshots(
            self,
            files: Mapping[str, FileSnapshot],
            names: set[str],
    ) -> list[FileSnapshot]:
        return [files[name] for name in names]

    # 6) Сравнение common и формирование списка InvalidFile
    def _diff_common(
            self,
            common_names: set[str],
            local_files: Mapping[str, FileSnapshot],
            remote_files: Mapping[str, FileSnapshot],
    ) -> list[InvalidFile]:
        diff_files: list[InvalidFile] = []

        for name in common_names:
            local = local_files[name]
            remote = remote_files[name]

            if local.size != remote.size:
                diff_files.append(
                    InvalidFile(
                        name,
                        f"Размеры: local={local.size}, remote={remote.size}",
                    )
                )

            if local.md5_hash != remote.md5_hash:
                diff_files.append(
                    InvalidFile(
                        name,
                        f"Хэш файла: local={local.md5_hash}, remote={remote.md5_hash}",
                    )
                )

        return diff_files

    # 7) Финальная сборка и сортировка
    def _build_plan(
            self,
            to_delete: list[FileSnapshot],
            to_download: list[FileSnapshot],
            diff_files: list[InvalidFile],
    ) -> DiffPlan:
        return DiffPlan(
            to_delete=sorted(to_delete, key=lambda f: f.path),
            to_download=sorted(to_download, key=lambda f: f.path),
            diff_files=sorted(diff_files, key=lambda f: f.path),
        )

    def _snapshot_name_to_stop_key(self, path: str) -> str:
        stem, suffix = os.path.splitext(posixpath.basename(path))
        base, sep, tail = stem.rpartition("_")  # только последний "_"
        if sep and tail.isdigit():  # хвост = номер релиза
            stem = base

        return f"{stem}{suffix}"

    def apply_stop_set(self, data: DiffInput, downloads: set[str]) -> set[str]:
        stop_set: set[str] = {x.strip() for x in data.context.app.stop_list}

        to_remove = set()

        for item in downloads:
            if self._snapshot_name_to_stop_key(item) in stop_set:
                to_remove.add(item)
                logger.warning(
                    "Файл {file} копироваться не будет <-- STOP LIST",
                    file=item,
                )

        return to_remove

    def apply_add_set(self, data: DiffInput, dpwnloads: set[str]) -> set[str]:
        to_add: set[str] = {x for x in data.context.app.add_list}

        return to_add
