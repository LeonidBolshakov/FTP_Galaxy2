"""
transfer_service.py

Сервис загрузки набора файлов (по снапшотам) в «официальную» директорию NEW.

Основной сценарий:
1) Убедиться, что директории local/NEW/OLD существуют.
2) Если NEW не пустая — спросить пользователя (продолжить / начать заново / стоп).
3) Привести NEW в пригодное состояние (удалить нулевые файлы, проверить что в NEW нет папок).
4) Скачать файлы из списка снапшотов в NEW.
5) Вернуть (успех, отчёт).

Отчёт (ReportItems) используется для фиксации фатальных ситуаций (например, пользователь отменил работу,
или в NEW обнаружен не файл).
"""

from pathlib import Path
from enum import Enum, auto
from typing import assert_never, Callable

from loguru import logger

from SYNC_APP.APP.dto import (
    TransferInput,
    FileSnapshot,
    Ftp,
    ReportItems,
    ReportItem,
    StatusReport,
)
from GENERAL.errors import DownloadFileError
from SYNC_APP.INFRA.utils import prompt_action, clean_dir, fs_call, safe_mkdir


# fmt: off
class NewDirAction(Enum):
    """Варианты действий, если директория NEW не пустая."""
    CONTINUE                    = auto()    # Докачиваем в текущую NEW
    RESTART                     = auto()    # Начинаем заново: чистим NEW и OLD
    STOP                        = auto()    # Выходим из программы
# fmt: on


# Меню выбора действия при обнаружении файлов в NEW.
MENU = (
    "Директория NEW содержит компоненты системы.",
    "[П] Продолжаем (докачка)",
    "[Н] Начинаем заново (очистим NEW и OLD)",
    "[С] Стоп — прекращаем работу",
)

# fmt: off
# Раскладка горячих клавиш с учётом RU/EN + популярных вариантов (p/g, n/y, s/c).
MAPPING = {
    "п": NewDirAction.CONTINUE, "p": NewDirAction.CONTINUE, "g": NewDirAction.CONTINUE,
    "н": NewDirAction.RESTART,  "n": NewDirAction.RESTART,  "y": NewDirAction.RESTART,
    "с": NewDirAction.STOP,     "s": NewDirAction.STOP,     "c": NewDirAction.STOP,
}
# fmt: on

# Тип «функции выбора» действия для NEW: позволяет заменить UI на автологику/тестовый стаб.
NewDirSelector = Callable[[Path], NewDirAction]


def interface_new_dir_selector(_: Path) -> NewDirAction:
    """
    UI-реализация выбора действия для NEW.

    Возвращает выбранное пользователем действие через prompt_action().

    Args:
        _: путь к NEW (в текущей реализации не используется).

    Returns:
        NewDirAction: действие пользователя.
    """
    return prompt_action(mapping=MAPPING, menu=MENU)


class TransferService:
    """
    Сервис, который скачивает набор файлов по снапшотам в директорию NEW.

    Особенности:
    - При наличии файлов в NEW требует решения пользователя (continue/restart/stop).
    - Удаляет нулевые файлы в NEW (чтобы принудить повторную загрузку).
    - Фиксирует фатальные ситуации в self.report и возвращает его вызывающему коду.

    Возврат метода run():
        (ok, report)
        ok == True  -> отчёт пуст (ошибок/фаталов не зафиксировано)
        ok == False -> в отчёте есть записи (как минимум FATAL)
    """

    def __init__(self, new_dir_selector: NewDirSelector | None = None) -> None:
        """
        Args:
            new_dir_selector: функция выбора действия при непустой NEW.
                Если не передана — используется интерактивная interface_new_dir_selector.

        Side effects:
            Создаёт контейнер отчёта (ReportItems), в который методы добавляют ReportItem.
        """
        self.new_dir_selector = new_dir_selector or interface_new_dir_selector
        self.report = ReportItems()

    def run(self, data: TransferInput) -> tuple[bool, ReportItems]:
        """
        Выполнить перенос/скачивание файлов в NEW.

        Steps:
        1) Подготовить директории local/NEW/OLD.
        2) Проиндексировать снапшоты по имени (для потенциальных проверок/санации).
        3) Если NEW не пустая — спросить действие пользователя (continue/restart/stop).
        4) Очистить/проверить содержимое NEW (удалить нулевые файлы, проверить что это файлы).
        5) Скачать указанные снапшоты в NEW.

        Args:
            data: TransferInput с ftp-клиентом, списком снапшотов для загрузки и контекстом путей.

        Returns:
            tuple[bool, ReportItems]: (успех, отчёт).
        """

        self.report = ReportItems()
        ftp = data.ftp
        snapshots_for_loading = data.snapshots_for_loading

        local_dir, new_dir, old_dir = self._prepare_official_dirs(data)
        schnapsots_for_loading_by_name = self._index_snapshots_by_name(
            snapshots_for_loading
        )

        # Если NEW содержит файлы — требуем решение пользователя (продолжать/перезапуск/стоп).
        good = self._ensure_new_and_old_dirs_are_ready(new_dir=new_dir, old_dir=old_dir)
        if not good:
            return good, self.report

        # Лёгкая “санация” NEW: в текущей версии — только проверка на “это файл” + удаление нулевых.
        self._sanitize_new_dir(new_dir=new_dir)

        # Скачиваем снапшоты в NEW.
        self._download_files_from_snapshots(
            ftp=ftp, snapshots_to_download=snapshots_for_loading, new_dir=new_dir
        )
        return False if self.report else True, self.report

    def _prepare_official_dirs(self, data: TransferInput) -> tuple[Path, Path, Path]:
        """
        Подготовить «официальные» директории local/NEW/OLD.

        Создаёт директории при необходимости.

        Args:
            data: TransferInput с путями в data.context.app.*

        Returns:
            (local_dir, new_dir, old_dir)
        """

        local_dir = data.context.app.local_dir
        new_dir = data.context.app.new_dir
        old_dir = data.context.app.old_dir
        safe_mkdir(local_dir)
        safe_mkdir(new_dir)
        safe_mkdir(old_dir)
        return local_dir, new_dir, old_dir

    def _index_snapshots_by_name(
            self, snapshots: list[FileSnapshot]
    ) -> dict[str, FileSnapshot]:
        """
        Проиндексировать снапшоты по имени файла.

        Удобно, если нужно быстро проверять “ожидается ли файл” по имени.

        Args:
            snapshots: список FileSnapshot.

        Returns:
            dict[name -> FileSnapshot]
        """

        return {snap.name: snap for snap in snapshots}

    def _download_files_from_snapshots(
            self, ftp: Ftp, snapshots_to_download: list[FileSnapshot], new_dir: Path
    ) -> None:
        """
        Скачать список файлов по снапшотам.

        Args:
            ftp: FTP-обёртка/клиент.
            snapshots_to_download: список FileSnapshot, которые нужно скачать.
            new_dir: директория назначения (NEW).
        """
        for snapshot in snapshots_to_download:
            self._download_file_from_snapshot(
                ftp=ftp, snapshot=snapshot, new_dir=new_dir
            )

    def _download_file_from_snapshot(
            self, ftp: Ftp, snapshot: FileSnapshot, new_dir: Path
    ) -> None:
        """
        Скачать один файл, описанный снапшотом.

        В случае DownloadFileError:
        - запись в отчёт не добавляется (только лог),
          предполагается, что “полный контроль”/валидация будет в другом слое.

        Args:
            ftp: FTP-обёртка/клиент.
            snapshot: снапшот файла (имя/размер/хэш и т.п. — зависит от FileSnapshot).
            new_dir: директория назначения (NEW).
        """
        file_name = snapshot.name
        local_full_path = new_dir / file_name

        try:
            ftp.download_file(
                snapshot=snapshot,
                local_full_path=local_full_path,
            )
        except DownloadFileError as e:
            logger.error(
                "Файл {file} не загружен в директорию {folder}\n{e}",
                file=file_name,
                folder=new_dir,
                e=e,
            )

            self.report.append(
                ReportItem(
                    name=file_name,
                    status=StatusReport.ERROR,
                    comment=f"Файл не загружен на локальный диск\n{e}",
                )
            )

    def _sanitize_new_dir(self, new_dir: Path) -> None:
        """
        Привести NEW в “аккуратное” состояние перед докачкой.

        Текущие действия:
        — убедиться, что каждый элемент в NEW — файл (иначе FATAL в отчёт),
        — удалить файлы нулевого размера.

        Args:
            new_dir: директория NEW.
        """
        for local_file_path in new_dir.iterdir():
            self._make_sure_is_file(local_file_path=local_file_path)
            self._unlink_zero_file(local_file_path=local_file_path)

    def _make_sure_is_file(self, local_file_path: Path) -> None:
        """
        Проверить, что элемент в NEW — именно файл.

        Если это не файл (например, каталог) — фиксируем FATAL в отчёте.

        Args:
            local_file_path: путь к элементу из NEW.
        """
        if local_file_path.is_file():
            return

        self.report.append(
            ReportItem(
                name=local_file_path.name,
                status=StatusReport.FATAL,
                comment=f"{local_file_path.name} не является файлом или не существует в директории NEW",
            )
        )

    def _unlink_zero_file(self, local_file_path: Path) -> None:
        """
        Удалить файл нулевого размера.

        Нулевой размер трактуется как “битая/недокачанная” сущность, которую лучше скачать заново.

        Args:
            local_file_path: путь к файлу в NEW.
        """
        if self.get_local_file_size(local_file_path) == 0:
            fs_call(
                local_file_path,
                "Удаление пустого файла",
                lambda: local_file_path.unlink(),
            )

    def _ensure_new_and_old_dirs_are_ready(
        self,
        *,
        new_dir: Path,
        old_dir: Path,
    ) -> bool:
        """
        Убедиться, что NEW/OLD готовы к работе.

        Если NEW пустая — всё ок.
        Если NEW не пустая — спрашиваем действие пользователя:
        - STOP: фиксируем FATAL и прекращаем (return False)
        - RESTART: очищаем NEW и OLD, продолжаем (return True)
        - CONTINUE: продолжаем докачку в текущую NEW (return True)

        Args:
            new_dir: директория NEW.
            old_dir: директория OLD (используется при RESTART для очистки).

        Returns:
            bool: True — можно продолжать; False — работу нужно прервать.
        """

        try:
            items_dir = list(new_dir.iterdir())
        except OSError as e:
            raise RuntimeError(f"Ошибка при чтении директории {new_dir}") from e

        if not items_dir:
            return True

        logger.info(
            "В директории {new_dir} обнаружены компоненты системы", new_dir=new_dir
        )

        action = self.new_dir_selector(new_dir)
        match action:
            case NewDirAction.STOP:
                self.report.append(
                    ReportItem(
                        name="",
                        status=StatusReport.ERROR,
                        comment="Пользователь отказался продолжать работу",
                    )
                )
                logger.error("Пользователь отказался продолжать работу")
                return False

            case NewDirAction.RESTART:
                logger.info("Пользователь решил начать скачивание заново")
                clean_dir(new_dir)
                clean_dir(old_dir)

            case NewDirAction.CONTINUE:
                logger.info("Пользователь решил продолжить ранее начатое скачивание")

            case _:
                assert_never(action)

        return True

    def get_local_file_size(self, path: Path) -> int:
        """
        Безопасно получить размер локального файла.

        Обёртка над stat().st_size через fs_call().
        Если файл отсутствует — возвращает 0.

        Args:
            path: путь к файлу.

        Returns:
            int: размер в байтах или 0, если файл не найден.
        """
        try:
            local_size = fs_call(
                path, "Получение размера файла", lambda: path.stat().st_size
            )
        except FileNotFoundError:
            local_size = 0

        return local_size
