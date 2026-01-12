from loguru import logger
import os
import posixpath
from pathlib import PurePosixPath
from typing import Mapping

from SRC.SYNC_APP.APP.dto import (
    DiffPlan,
    DiffInput,
    FileSnapshot,
    ModeDiffPlan,
    ReportItem,
    ReportItems,
)


class DiffPlanner:
    """Строит план синхронизации локальной директории с удалённым (FTP).

    Назначение:
        — определить, какие файлы нужно удалить локально (лишние),
        — какие нужно скачать (отсутствуют локально),
        — какие присутствуют в обоих местах, но отличаются по размеру/хэшу.

    Важно:
        Сравнение производится по *имени файла* (basename), без учёта каталогов.
        Для remote-части ключи нормализуются как Path(remote_path).name.
        Это означает, что два разных remote-пути с одинаковым basename считаются конфликтом.
    """

    def run(self, data: DiffInput) -> DiffPlan:
        """Сравнивает локальные и удалённые файлы и возвращает DiffPlan.

        Алгоритм:
            1) Берёт локальные файлы как есть: `data.local.files` (dict[name -> FileSnapshot]).
            2) Преобразует удалённые файлы к словарю `basename -> FileSnapshot`.
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
                - report_items: список расхождений для файлов, присутствующих в обоих снимках.
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
        download_names: set[str] = self._apply_stop_lists(data, raw_download_names)

        to_delete: list[FileSnapshot] = self._collect_snapshots(
            local_files, delete_names
        )
        to_download: list[FileSnapshot] = self._collect_snapshots(
            remote_files, download_names
        )

        report_items: ReportItems = self._diff_common(
            common_names, local_files, remote_files
        )

        return self._build_plan(to_delete, to_download, report_items)

    def _remote_files_by_basename(
            self,
            remote_files: Mapping[str, FileSnapshot],
    ) -> dict[str, FileSnapshot]:
        """Нормализация remote: ключ -> basename"""

        return {PurePosixPath(p).name: snap for p, snap in remote_files.items()}

    def _names(self, files: Mapping[str, FileSnapshot]) -> set[str]:
        """Получение множества имён (ключей словаря)"""
        return set(files)

    # -------
    # --- Операции над множествами имён
    # -------
    def _common_names(self, local: set[str], remote: set[str]) -> set[str]:
        return local & remote

    def _delete_names(self, local: set[str], remote: set[str]) -> set[str]:
        return local - remote

    def _download_names(self, local: set[str], remote: set[str]) -> set[str]:
        return remote - local

    # -------

    def _apply_stop_lists(self, data: DiffInput, download: set[str]) -> set[str]:
        """Применение stop/add списков (если включено)"""

        # работаем с копией, чтобы не мутировать входной set снаружи
        result = set(download)

        result |= self.apply_add_set(data, result)

        if data.context.use_stop_list == ModeDiffPlan.USE_STOP_LIST:
            result -= self.apply_stop_set(data, result)

        if len(result) <= len(data.context.app.add_list):
            result.clear()

        return result

    def _collect_snapshots(
            self,
            files: Mapping[str, FileSnapshot],
            names: set[str],
    ) -> list[FileSnapshot]:
        """Сбор FileSnapshot по именам файлов"""

        return [files[name] for name in names]

    def _diff_common(
            self,
            common_names: set[str],
            local_files: Mapping[str, FileSnapshot],
            remote_files: Mapping[str, FileSnapshot],
    ) -> ReportItems:
        """Сравнение common и формирование списка InvalidFile"""

        report_items = ReportItems()

        for name in common_names:
            local = local_files[name]
            remote = remote_files[name]

            if local.size != remote.size:
                report_items.append(
                    ReportItem(
                        name,
                        f"Размеры: local={local.size}, remote={remote.size}",
                    )
                )

            if local.md5_hash != remote.md5_hash:
                report_items.append(
                    ReportItem(
                        name,
                        f"Хэш файла: local={local.md5_hash}, remote={remote.md5_hash}",
                    )
                )

        return report_items

    def _build_plan(
            self,
            to_delete: list[FileSnapshot],
            to_download: list[FileSnapshot],
            report_items: ReportItems,
    ) -> DiffPlan:
        """Финальная сборка и сортировка"""

        return DiffPlan(
            to_delete=sorted(to_delete, key=lambda f: f.name),
            to_download=sorted(to_download, key=lambda f: f.name),
            report_plan=sorted(report_items, key=lambda f: f.name),
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
