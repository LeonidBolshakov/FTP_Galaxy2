from pathlib import Path, PurePosixPath
from enum import Enum, auto
import os
import sys
from typing import assert_never

from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    TransferInput,
    FileSnapshot,
    LocalFileAccessError,
    DownloadFileError,
    ConfigError,
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
    "[С] Прекращаем работу\n"
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
        snapshots = data.snapshots

        local_dir, new_dir, old_dir = self._prepare_official_dirs(data)
        snapshots_by_name = self._index_snapshots_by_name(snapshots)

        valid_new_snapshots = self._build_new_dir_snapshots(
            new_dir=new_dir,
            old_dir=old_dir,
            snapshots_by_name=snapshots_by_name,
        )

        snapshots_to_download = self._select_snapshots_to_download(
            snapshots, valid_new_snapshots
        )

        self._sanitize_new_dir(new_dir=new_dir, snapshots=snapshots_by_name)

        self._download_snapshot_files(ftp, snapshots_to_download, new_dir)

    @staticmethod
    def _assert_same_fs(old_dir: Path, local_dir: Path) -> None:
        try:
            local_stat = local_dir.stat()
        except OSError as e:
            raise ConfigError(f"Некорректный путь local_dir: {local_dir!r}") from e

        try:
            old_stat = old_dir.stat()
        except OSError as e:
            raise ConfigError(f"Некорректный путь old_dir: {old_dir!r}") from e

        if local_stat.st_dev != old_stat.st_dev:
            # drive удобно на Windows, но на POSIX может быть пустым — поэтому оставим ещё и полный путь
            raise ConfigError(
                "Папки local_dir и old_dir должны быть в одном файловом разделе:\n"
                f"local_dir={local_dir} (drive={local_dir.resolve().drive})\n"
                f"old_dir={old_dir} (drive={old_dir.resolve().drive})"
            )

    # --- 1) Подготовка директорий NEW/OLD
    def _prepare_official_dirs(self, data: TransferInput) -> tuple[Path, Path, Path]:
        local_dir = data.context.app.local_dir
        new_dir = data.context.app.new_dir_path
        old_dir = data.context.app.old_dir_path
        self.safe_mkdir(local_dir)
        self.safe_mkdir(new_dir)
        self.safe_mkdir(old_dir)
        return local_dir, new_dir, old_dir

    # --- 2) Индексация снапшотов по имени файла
    def _index_snapshots_by_name(
            self, snapshots: list[FileSnapshot]
    ) -> dict[str, FileSnapshot]:
        return {self._snapshot_name(snap): snap for snap in snapshots}

    # --- 3) Определение, что ещё нужно скачать
    def _select_snapshots_to_download(
            self,
            snapshots: list[FileSnapshot],
            valid_new_snapshots: list[FileSnapshot],
    ) -> list[FileSnapshot]:
        valid_paths = {s.name for s in valid_new_snapshots}
        return [s for s in snapshots if s.name not in valid_paths]

    # --- 4) Загрузка файлов
    def _download_snapshot_files(
            self, ftp: Ftp, snapshots_to_download: list[FileSnapshot], new_dir: Path
    ) -> None:
        if snapshots_to_download:
            print("Загрузка файлов")

        for snapshot in snapshots_to_download:
            self._download_one_snapshot(ftp, snapshot, new_dir)

    # --- 5) Скачивание одного файла
    def _download_one_snapshot(
            self, ftp: Ftp, snapshot: FileSnapshot, new_dir: Path
    ) -> None:
        remote_name = snapshot.name
        local_name = Path(self._snapshot_name(snapshot))
        local_full_path = new_dir / local_name

        try:
            ftp.download_file(
                remote_item=self._ftp_item_from_snapshot(snapshot),
                local_full_path=local_full_path,
            )
        except DownloadFileError as e:
            try:
                local_name.unlink(missing_ok=True)
            except Exception:
                pass
            logger.error(
                "Файл {file} не загружен в директорию {dir}\n{e}",
                file=remote_name,
                dir=new_dir,
                e=e,
            )

    # --- 6) Построение FTPDirItem из снапшота
    def _ftp_item_from_snapshot(self, snapshot: FileSnapshot) -> FileSnapshot:
        return FileSnapshot(
            name=snapshot.name,
            size=snapshot.size,
            md5_hash=snapshot.md5_hash,
        )

    def safe_mkdir(self, dir_path: Path) -> None:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    def _sanitize_new_dir(
            self, new_dir: Path, snapshots: dict[str, FileSnapshot]
    ) -> None:
        for name in new_dir.iterdir():
            self._ensure_is_file_or_exit(new_dir=new_dir, name=name)
            if name.name not in snapshots:
                self._unknown_file(new_dir=new_dir, path=name)

    def _ensure_is_file_or_exit(self, new_dir: Path, name: Path) -> None:
        if (new_dir / name).is_file():
            return

        logger.error(
            "В директории {dir} найден не-файл: {item_in_dir}. Программа прекращает работу.",
            dir=new_dir,
            item_in_dir=name,
        )
        raise SystemExit(1)

    def _unknown_file(self, new_dir: Path, path: Path) -> None:
        logger.warning(
            "В директории {new_dir}\n"
            "обнаружен не запланированный к загрузке или уже загруженный файл {name}",
            new_dir=new_dir,
            path=path.name,
        )

    def _build_new_dir_snapshots(
        self,
        *,
        new_dir: Path,
        old_dir: Path,
        snapshots_by_name: dict[str, FileSnapshot],
    ) -> list[FileSnapshot]:
        """
        Если NEW пуста — просто строим локальный снапшот.
        Если NEW не пуста — спрашиваем пользователя: продолжить / начать заново / остановить.
        Возвращает то же, что select_size_matched_snapshots().
        """
        items_dir = list(new_dir.iterdir())
        if items_dir:
            logger.info(
                "В директории {new_dir} обнаружены компоненты системы", new_dir=new_dir
            )
            need_rescan_new_dir = self._process_nonempty_new_dir(
                new_dir=new_dir, old_dir=old_dir
            )
            if need_rescan_new_dir:
                items_dir = list(new_dir.iterdir())

        # CONTINUE или RESTART -> строим снапшот по текущему содержимому NEW
        return self._get_verified_snapshots_for_items_dir(
            items_dir=items_dir, snapshots_by_name=snapshots_by_name
        )

    def _process_nonempty_new_dir(self, new_dir: Path, old_dir: Path) -> bool:
        """
        Обрабатывает ситуацию, когда NEW не пустая:
        - STOP    -> завершает программу (SystemExit)
        - RESTART -> чистит NEW и OLD и сообщает, что NEW надо перечитать
        - CONTINUE-> ничего не чистит, перечитывать не нужно
        Возвращает: нужно ли заново считать содержимое NEW (bool).
        """
        action = self._prompt_new_dir_action()

        match action:
            case NewDirAction.STOP:
                logger.error("Пользователь отказался продолжать работу")
                raise SystemExit(1)

            case NewDirAction.RESTART:
                self.clean_dir(new_dir)
                self.clean_dir(old_dir)
                logger.info("Пользователь начал скачивание заново")
                print("Начинаем работать заново")
                return True  # перечитать NEW

            case NewDirAction.CONTINUE:
                logger.info("Пользователь продолжил ранее начатое скачивание")
                print("Продолжаем работать")
                return False  # перечитывать не надо

            case _:
                assert_never(action)

    def _is_pycharm_console(self) -> bool:
        return os.environ.get("PYCHARM_HOSTED") == "1"

    def _read_char_windows(self, prompt: str) -> str:
        # noinspection PyCompatibility
        import msvcrt  # Windows-only

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

    def _get_verified_snapshots_for_items_dir(
        self, items_dir: list[Path], snapshots_by_name: dict[str, FileSnapshot]
    ) -> list[FileSnapshot]:
        file_snapshots: list[FileSnapshot] = []
        for item_dir in items_dir:
            snap = snapshots_by_name.get(item_dir.name)
            if snap and snap.size == self.get_local_file_size(item_dir):
                file_snapshots.append(snap)

        return file_snapshots

    def clean_dir(self, dir_path: Path) -> None:
        for p in dir_path.iterdir():
            if p.is_file():
                p.unlink(missing_ok=True)

    def get_local_file_size(self, path: Path) -> int:
        local_size = 0
        try:
            local_size = path.stat().st_size
        except FileNotFoundError:
            local_size = 0
        except PermissionError as e:
            raise LocalFileAccessError(f"Нет доступа к {path}") from e
        except OSError as e:
            raise LocalFileAccessError(
                f"Ошибка файловой системы для {path}: {e}"
            ) from e

        return local_size

    def _snapshot_name(self, snap: FileSnapshot) -> str:
        return PurePosixPath(snap.name).name
