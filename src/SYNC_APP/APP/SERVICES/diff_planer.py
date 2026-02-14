"""Построение плана различий (diff-plan) между локальным и удалённым снимками.

Модуль реализует `DiffPlanner`, который:
— сравнивает наборы файлов по имени (basename) между локальным и удалённым снимками,
— формирует план действий: что удалить локально и что скачать с FTP,
— применяет add-list / stop-list (если включено),
— формирует отчёт (report) для файлов, исключённых stop листом.

Ограничения и допущения
-----------------------
- Сравнение выполняется по *имени файла* (ключу в `RepositorySnapshot.files`), без учёта каталогов.
- Несовпадение определяется только по `size` (hash здесь не используется).
- Файлы, которые "несовпадают" (mismatched), добавляются и в `to_delete`, и в `to_download` —
  удалить локальную версию и скачать заново.

Примечание про stop-list
------------------------
Режим применения stop-list задаётся в параметрах вызова программы как ключ --mode stop-list.
Планировщик (`DiffPlanner`) читает этот режим из `data.context`.
"""

from loguru import logger
from typing import Mapping
from operator import attrgetter
from dataclasses import dataclass

from SYNC_APP.INFRA.utils import name_file_to_name_component
from SYNC_APP.APP.dto import (
    DiffPlan,
    DiffInput,
    FileSnapshot,
    ModeDiffPlan,
    ReportItems,
    ReportItem,
    StatusReport,
)


@dataclass(slots=True, frozen=True)
class SyncPlan:
    """План, сформированный из сырых множеств имён.

    Attributes
    ----------
    to_delete
        Снимки файлов, которые есть локально, но отсутствуют на сервере.
    to_download
        Снимки файлов, которые есть на сервере, но отсутствуют локально (с учётом add/stop list).
    denied_download
        Имена файлов, которые попали в "кандидаты на скачивание", но были исключены stop-list.
    mismatched
        Файлы, которые есть и локально, и удалённо, но отличаются по размеру.
        (Здесь создаются "пустые" `FileSnapshot` с `size=None`)
    """

    to_delete: list[FileSnapshot]
    to_download: list[FileSnapshot]
    denied_download: set[str]
    mismatched: list[FileSnapshot]


class DiffPlanner:
    """Строит план синхронизации локальной директории с удалённым (FTP).

    Назначение:
        — определить, какие файлы нужно удалить локально (лишние),
        — какие нужно скачать (отсутствуют локально),
        — какие присутствуют в обоих местах, но отличаются по размеру/хэшу.

    Важно:
        Сравнение производится по *имени файла* (basename), без учёта каталогов.
    """

    def run(self, data: DiffInput) -> tuple[DiffPlan, bool, ReportItems]:
        """Сравнивает локальные и удалённые файлы и возвращает план + отчёт.

        Parameters
        ----------
        data : DiffInput
            Входные данные: два снимка (`local_snap`, `remote_snap`) и параметры
            применения stop-list/add-list.

        Returns
        -------
        tuple[DiffPlan, ReportItems]
            plan
                План действий: что удалить локально и что скачать.
            report
                Сообщения (в основном предупреждения) по файлам, исключённым stop-list.
        """
        sync_plan: SyncPlan = self._build_sync_plan(data)

        plan = self._build_plan(
            sync_plan.to_delete, sync_plan.to_download, sync_plan.mismatched
        )
        report = self._build_report(sync_plan.denied_download)

        is_valid = len(sync_plan.denied_download) == 0
        if (
                is_valid
                and len(plan.to_download) == 0
                and len(plan.to_delete) == 0
                and len(report) == 0
        ):
            report.append(
                ReportItem(
                    name="",
                    status=StatusReport.IMPORTANT_INFO,
                    comment="Обновлений нет. К скачиваню ничего не запланировано.",
                )
            )

        return plan, is_valid, report

    def _build_sync_plan(self, data: DiffInput) -> SyncPlan:
        """Формирует промежуточный `SyncPlan` из двух снимков.

        Parameters
        ----------
        data : DiffInput
            Содержит `local_snap.files` и `remote_snap.files` — отображения
            `имя_файла -> FileSnapshot`.

        Returns
        -------
        SyncPlan
            Промежуточная структура с вычисленными списками/множествами имён.
        """
        # local_snaps_files / remote_snaps_files — снимки файлов: {имя_файла -> FileSnapshot}
        local_snaps_files: dict[str, FileSnapshot] = data.local_snap.files
        remote_snaps_files: dict[str, FileSnapshot] = data.remote_snap.files

        local_names: set[str] = set(local_snaps_files)
        remote_names: set[str] = set(remote_snaps_files)

        common_names, raw_delete_names, raw_download_names = (
            self._compute_sync_name_sets(local_names, remote_names)
        )

        # download_names — итог к скачиванию после add_list/stop_list
        download_names, delete_names, names_denied_download = (
            self._apply_stop_add_lists(
                data=data,
                raw_download_names=raw_download_names,
                raw_delete_names=raw_delete_names,
                raw_remote_names=remote_names,
            )
        )

        # to_delete / to_download — собираем по рассчитанным именам
        to_delete = self._collect_snapshots(local_snaps_files, delete_names)
        to_download = self._collect_snapshots(remote_snaps_files, download_names)

        # missmathed — несоответствия среди common по size
        error_items = self._get_mismatched_files(
            common_names, local_snaps_files, remote_snaps_files
        )

        return SyncPlan(
            to_delete=to_delete,
            to_download=to_download,
            denied_download=names_denied_download,
            mismatched=error_items,
        )

    def _compute_sync_name_sets(
            self, local_names: set[str], remote_names: set[str]
    ) -> tuple[set[str], set[str], set[str]]:

        common_names = local_names & remote_names
        delete_names = local_names - remote_names
        raw_download_names = remote_names - local_names

        return common_names, delete_names, raw_download_names

    def _apply_stop_add_lists(
        self,
        data: DiffInput,
        raw_download_names: set[str],
            raw_delete_names: set[str],
            raw_remote_names: set[str],
    ) -> tuple[set[str], set[str], set[str]]:
        """Применяет add-list и stop-list к списку кандидатов на скачивание.

        Parameters
        ----------
        data : DiffInput
            Входные данные с конфигурацией (`data.context.app.add_list`, `stop_list`)
            и режимом применения stop-list.
        raw_download_names : set[str]
            Имена файлов, которые есть на сервере, но отсутствуют локально.
        raw_remote_names : set[str]
            Все имена удалённых файлов (используется, чтобы add-list не добавлял "несуществующее").

        Returns
        -------
        tuple[set[str], set[str]]
            download_names
                Итоговое множество имён к скачиванию.
            denied_download
                Имена, исключённые stop листом (будут отражены в отчёте).
        """
        if not raw_download_names:
            return set(), set(), set()

        # работаем с копией, чтобы не мутировать входной set
        result_downloads = set(raw_download_names)
        result_deletes = set(raw_delete_names)
        add_list = set(data.context.app.add_list or ())

        result_downloads |= add_list & raw_remote_names
        result_deletes |= add_list & raw_remote_names

        denied_download: set[str] = (
            set()
        )  # На случай если следующие операторы не заполнят exclude
        if data.context.mode_stop_list == ModeDiffPlan.USE_STOP_LIST:
            denied_download = self._get_files_excluded_by_stop_list(
                data, result_downloads
            )
            result_downloads -= denied_download

        return result_downloads, result_deletes, denied_download

    def _collect_snapshots(
        self,
        files: Mapping[str, FileSnapshot],
        names: set[str],
    ) -> list[FileSnapshot]:
        """Собирает `FileSnapshot` по набору имён.

        Parameters
        ----------
        files : Mapping[str, FileSnapshot]
            Отображение `имя -> FileSnapshot`.
        names : set[str]
            Имена, для которых нужно взять снимки.

        Returns
        -------
        list[FileSnapshot]
            Список найденных снимков (имена, отсутствующие в `files`, пропускаются).
        """
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
    ) -> list[FileSnapshot]:
        """Находит файлы, которые присутствуют в обоих снимках, но отличаются по размеру.

        Parameters
        ----------
        common_names : set[str]
            Имена, присутствующие и локально, и на сервере.
        local_file_snapshots : Mapping[str, FileSnapshot]
            Локальные снимки файлов.
        remote_file_snapshots : Mapping[str, FileSnapshot]
            Удалённые снимки файлов.

        Returns
        -------
        list[FileSnapshot]
            Список файлов-«конфликтов». Для каждого создаётся новый `FileSnapshot`
            с `size=None` и `md5_hash=None`, чтобы отметить факт несовпадения.
        """
        error_items: list[FileSnapshot] = []

        for name in common_names:
            local = local_file_snapshots[name]
            remote = remote_file_snapshots[name]

            if local.size != remote.size:
                error_items.append(FileSnapshot(name=name, size=None, md5_hash=None))

        return error_items

    def _build_plan(
        self,
        to_delete: list[FileSnapshot],
        to_download: list[FileSnapshot],
            missmathed: list[FileSnapshot],
    ) -> DiffPlan:
        """Собирает и сортирует итоговый `DiffPlan`.

        Parameters
        ----------
        to_delete : list[FileSnapshot]
            Лишние локальные файлы (к удалению).
        to_download : list[FileSnapshot]
            Отсутствующие локально файлы (к скачиванию).
        missmathed : list[FileSnapshot]
            Файлы, которые есть в обоих местах, но отличаются (конфликты).

        Returns
        -------
        DiffPlan
            Итоговый план. Конфликтные файлы добавляются и в `to_delete`, и в `to_download`
            (паттерн "удалить и скачать заново").
        """
        merge_delete = to_delete + missmathed
        merge_download = to_download + missmathed

        key = attrgetter("name")

        return DiffPlan(
            to_delete=sorted(merge_delete, key=key),
            to_download=sorted(merge_download, key=key),
        )

    def _get_files_excluded_by_stop_list(
        self, data: DiffInput, downloads: set[str]
    ) -> set[str]:
        """Возвращает подмножество `downloads`, исключённое по stop-list.

        Parameters
        ----------
        data : DiffInput
            Контекст с `data.context.app.stop_list`.
        downloads : set[str]
            Имена файлов, рассматриваемых к скачиванию.

        Returns
        -------
        set[str]
            Имена файлов, которые попали под stop-list.
        """
        stop_list_set: set[str] = {x.strip() for x in data.context.app.stop_list}

        excluded = set()

        for item in sorted(downloads):
            if name_file_to_name_component(item) in stop_list_set:
                excluded.add(item)
                logger.warning(
                    "Файл {file} копироваться не будет <-- STOP LIST",
                    file=item,
                )

        return excluded

    def _build_report(self, denied_download: set[str]) -> ReportItems:
        """Формирует отчёт по файлам, исключённым stop-list.

        Parameters
        ----------
        denied_download : set[str]
            Имена файлов, исключённых stop-list.

        Returns
        -------
        ReportItems
            Список `ReportItem` уровня WARNING.
        """
        report: ReportItems = []
        for name in denied_download:
            report.append(
                ReportItem(
                    name=name,
                    status=StatusReport.WARNING,
                    comment="Файл запланирован к скачиванию, но находится в stop листе. Скачиваться не будет",
                )
            )

        return report
