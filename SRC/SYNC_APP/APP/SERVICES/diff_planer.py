from loguru import logger
import os
import posixpath
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
    """

    def run(self, data: DiffInput) -> DiffPlan:
        """Сравнивает локальные и удалённые файлы и возвращает DiffPlan.

        Алгоритм:
            1) Берёт локальные файлы как есть: `data.local.files` (dict[name -> FileSnapshot]).
            2) По множествам ключей вычисляет:
               - to_delete   = local - remote
               - to_download = remote - local
               - common      = local ∩ remote
            3) Для common сравнивает пары FileSnapshot по size и формирует список ReportItem.

        Args:
            data: DiffInput, содержащий два снимка: local и remote.

        Returns:
            DiffPlan:
                - to_delete: отсортированный список FileSnapshot, которые есть локально, но отсутствуют на сервере;
                - to_download: отсортированный список FileSnapshot, которые есть на сервере, но отсутствуют локально;
                - report_items: список несовпадающих файлов, присутствующих в обоих снимках.
        """

        # local_files / remote_files — снимки файлов: {имя_файла -> FileSnapshot}
        local_files: dict[str, FileSnapshot] = data.local.files
        remote_files: dict[str, FileSnapshot] = data.remote.files

        # local_names / remote_names — только имена файлов (ключи словарей)
        local_names: set[str] = set(local_files)
        remote_names: set[str] = set(remote_files)

        # common_names — файлы, которые есть и локально, и на сервере
        common_names = local_names & remote_names

        # delete_names — “лишние локальные”: есть локально, но нет на сервере
        delete_names = local_names - remote_names

        # raw_download_names — “нужно скачать”: есть на сервере, но нет локально
        raw_download_names = remote_names - local_names

        # download_names — итог к скачиванию после add_list/stop_list
        download_names = self._apply_add_stop_lists(
            data=data,
            raw_download_names=raw_download_names,
            remote_names=remote_names,
        )

        # to_delete / to_download — сами FileSnapshot по рассчитанным именам
        to_delete = self._collect_snapshots(local_files, delete_names)
        to_download = self._collect_snapshots(remote_files, download_names)

        # report_items — несоответствия среди common (пока только size)
        report_items = self._get_mismatched_files(
            common_names, local_files, remote_files
        )

        return self._build_plan(to_delete, to_download, report_items)

    def _apply_add_stop_lists(
        self,
        data: DiffInput,
        raw_download_names: set[str],
        remote_names: set[str],
    ) -> set[str]:
        """Применение add/stop списков (если включено)"""
        if not raw_download_names:
            return set()

        # работаем с копией, чтобы не мутировать входной set снаружи
        result = set(raw_download_names)
        add_list = set(data.context.app.add_list or ())

        result |= add_list & remote_names

        if data.context.use_stop_list == ModeDiffPlan.USE_STOP_LIST:
            result -= self._get_files_excluded_by_stop_list(data, result)

        return result

    def _collect_snapshots(
        self,
        files: Mapping[str, FileSnapshot],
        names: set[str],
    ) -> list[FileSnapshot]:
        """Сбор FileSnapshot по именам файлов"""

        collected = []
        for name in names:
            item = files.get(name)
            if item is None:
                continue
            collected.append(item)

        return collected

    def _get_mismatched_files(
        self,
        common_names: set[str],
        local_file_snapshots: Mapping[str, FileSnapshot],
        remote_file_snapshots: Mapping[str, FileSnapshot],
    ) -> ReportItems:
        """Сравнение common и формирование списка ReportItem"""

        report_items = ReportItems()

        for name in common_names:
            local = local_file_snapshots[name]
            remote = remote_file_snapshots[name]

            if local.size != remote.size:
                report_items.append(
                    ReportItem(
                        name,
                        f"Размеры: local={local.size}, remote={remote.size} не равны",
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

    def _get_files_excluded_by_stop_list(
        self, data: DiffInput, downloads: set[str]
    ) -> set[str]:
        """Вернёт подмножество downloads, которое надо исключить по stop_list."""

        stop_list_set: set[str] = {x.strip() for x in data.context.app.stop_list}

        excluded = set()

        for item in sorted(downloads):
            if self._snapshot_name_to_stop_key(item) in stop_list_set:
                excluded.add(item)
                logger.warning(
                    "Файл {file} копироваться не будет <-- STOP LIST",
                    file=item,
                )

        return excluded
