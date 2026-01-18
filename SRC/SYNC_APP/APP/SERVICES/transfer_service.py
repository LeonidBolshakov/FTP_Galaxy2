from os import unlink
from pathlib import Path
from enum import Enum, auto
import os
import sys
from typing import assert_never, Callable, TypeVar

from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    TransferInput,
    FileSnapshot,
    LocalFileAccessError,
    DownloadFileError,
    Ftp,
)


# fmt: off
class NewDirAction(Enum):
    CONTINUE                    = auto()    # Докачиваем в текущую NEW
    RESTART                     = auto()    # Начинаем заново: чистим NEW и OLD
    STOP                        = auto()    # Выходим из программы
# fmt: on


MENU = (
    "Директория NEW содержит компоненты системы.\n"
    "[П] Продолжаем (докачка)\n"
    "[Н] Начинаем заново (очистим NEW и OLD)\n"
    "[С] Стоп - прекращаем работу\n"
)

# fmt: off
MAPPING = {
    "п": NewDirAction.CONTINUE, "p": NewDirAction.CONTINUE, "g": NewDirAction.CONTINUE,
    "н": NewDirAction.RESTART,  "n": NewDirAction.RESTART,  "y": NewDirAction.RESTART,
    "с": NewDirAction.STOP,     "s": NewDirAction.STOP,     "c": NewDirAction.STOP,
}
# fmt: on


class TransferService:
    def run(self, data: TransferInput) -> None:
        ftp = data.ftp
        snapshots_for_loading = data.schnapsots_for_loading

        local_dir, new_dir, old_dir = self._prepare_official_dirs(data)
        schnapsots_for_loading_by_name = self._index_snapshots_by_name(
            snapshots_for_loading
        )

        self._ensure_new_and_old_dirs_are_ready(new_dir=new_dir, old_dir=old_dir)
        self._sanitize_new_dir(
            new_dir=new_dir, snapshots_by_name=schnapsots_for_loading_by_name
        )

        self._download_files_from_snapshots(
            ftp=ftp, snapshots_to_download=snapshots_for_loading, new_dir=new_dir
        )

    def _prepare_official_dirs(self, data: TransferInput) -> tuple[Path, Path, Path]:
        """Подготовка директорий NEW/OLD"""

        local_dir = data.context.app.local_dir
        new_dir = data.context.app.new_dir_path
        old_dir = data.context.app.old_dir_path
        self.safe_mkdir(local_dir)
        self.safe_mkdir(new_dir)
        self.safe_mkdir(old_dir)
        return local_dir, new_dir, old_dir

    def _index_snapshots_by_name(
            self, snapshots: list[FileSnapshot]
    ) -> dict[str, FileSnapshot]:
        """Индексация снапшотов по имени файла"""

        return {snap.name: snap for snap in snapshots}

    def _download_files_from_snapshots(
            self, ftp: Ftp, snapshots_to_download: list[FileSnapshot], new_dir: Path
    ) -> None:
        """Загрузка файлов"""
        print("Загрузка файлов")

        for snapshot in snapshots_to_download:
            self._download_file_from_snapshot(
                ftp=ftp, snapshot=snapshot, new_dir=new_dir
            )

    def _download_file_from_snapshot(
            self, ftp: Ftp, snapshot: FileSnapshot, new_dir: Path
    ) -> None:
        """Скачивание одного файла"""
        file_name = snapshot.name
        local_full_path = new_dir / file_name

        try:
            ftp.download_file(
                snapshot=snapshot,
                local_full_path=local_full_path,
            )
        except DownloadFileError as e:
            logger.error(
                "Файл {file} не загружен в директорию {dir}\n{e}",
                file=file_name,
                dir=new_dir,
                e=e,
            )

    @staticmethod
    def safe_mkdir(dir_path: Path) -> None:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    def _sanitize_new_dir(
            self, new_dir: Path, snapshots_by_name: dict[str, FileSnapshot]
    ) -> None:
        for local_file_path in new_dir.iterdir():
            self._make_sure_is_file(local_file_path=local_file_path)
            self._make_sure_file_known(
                local_file_path=local_file_path, snapshots_by_name=snapshots_by_name
            )
            self._unlink_zero_file(local_file_path=local_file_path)

    @staticmethod
    def _make_sure_is_file(local_file_path: Path) -> None:
        if local_file_path.is_file():
            return

        logger.error(
            "Найден не-файл: {local_file_path}. Программа прекращает работу.",
            local_file_path=local_file_path,
        )
        raise SystemExit(1)

    def _make_sure_file_known(
            self, local_file_path: Path, snapshots_by_name: dict[str, FileSnapshot]
    ) -> None:
        if local_file_path.name not in snapshots_by_name:
            logger.warning(
                "Обнаружен не запланированный к загрузке или уже загруженный файл {local_file_path}",
                local_file_path=local_file_path,
            )

    def _unlink_zero_file(self, local_file_path: Path) -> None:
        if self.get_local_file_size(local_file_path) == 0:
            self._fs_call(
                local_file_path,
                "Удаление пустого файла",
                lambda: unlink(local_file_path),
            )

    def _ensure_new_and_old_dirs_are_ready(
        self,
        *,
        new_dir: Path,
        old_dir: Path,
    ) -> None:

        items_dir = list(new_dir.iterdir())
        if not items_dir:
            return

        logger.info(
            "В директории {new_dir} обнаружены компоненты системы", new_dir=new_dir
        )

        action = self._prompt_new_dir_action()
        match action:
            case NewDirAction.STOP:
                logger.error("Пользователь отказался продолжать работу")
                raise SystemExit(1)

            case NewDirAction.RESTART:
                logger.info("Пользователь решил начать скачивание заново")
                print("Начинаем работать заново")
                self.clean_dir(new_dir)
                self.clean_dir(old_dir)

            case NewDirAction.CONTINUE:
                logger.info("Пользователь решил продолжить ранее начатое скачивание")
                print("Продолжаем работать")

            case _:
                assert_never(action)

    def _is_pycharm_console(self) -> bool:
        return os.environ.get("PYCHARM_HOSTED") == "1"

    def _read_char_windows(self, prompt: str) -> str:
        # noinspection PyCompatibility
        import msvcrt

        print(prompt, end="", flush=True)
        ch = msvcrt.getwch()
        print(ch)  # эхо
        return ch

    def _prompt_new_dir_action(self) -> NewDirAction:
        use_msvcrt = (
            sys.platform == "win32"
            and sys.stdin.isatty()
            and not self._is_pycharm_console()
        )

        read = self._read_char_windows if use_msvcrt else input

        print(MENU, end="")
        while True:
            raw = read("> ").strip()
            key = raw[:1].lower() if raw else ""
            action = MAPPING.get(key)
            if action is not None:
                return action
            print("Неверный выбор. Ожидается П/Н/С.")

    def clean_dir(self, dir_path: Path) -> None:
        try:
            dir_path_iter = dir_path.iterdir()
        except FileNotFoundError:
            return

        for p in dir_path_iter:
            if p.is_file():
                try:
                    self._fs_call(p, "удаление", lambda: p.unlink(missing_ok=True))
                except FileNotFoundError:
                    continue
            else:
                raise LocalFileAccessError(
                    f"{p} каталог или другой объект. Переместите или удалите его и другие объекты"
                )

    T = TypeVar("T")

    def _fs_call(self, path: Path, action: str, fn: Callable[[], T]) -> T:
        try:
            return fn()
        except PermissionError as e:
            raise LocalFileAccessError(f"Нет доступа к{path}") from e
        except OSError as e:
            raise LocalFileAccessError(
                f"Ошибка файловой системы при {action} для {path}:\n{e}"
            ) from e

    def get_local_file_size(self, path: Path) -> int:
        try:
            local_size = self._fs_call(
                path, "Получение размера файла", lambda: path.stat().st_size
            )
        except FileNotFoundError:
            local_size = 0

        return local_size
