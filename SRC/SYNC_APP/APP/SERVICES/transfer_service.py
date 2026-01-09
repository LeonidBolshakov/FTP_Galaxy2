from pathlib import Path
from enum import Enum, auto
import os
import sys

from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    TransferInput,
    TransferMode,
    FTPInput,
    FTPDirItem,
    FileSnapshot,
    LocalFileAccessError,
    DownloadFileError,
)
from SRC.SYNC_APP.ADAPTERS.ftp import Ftp


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

        mode = data.mode
        if mode == TransferMode.download:
            self._download(data)
        elif mode == TransferMode.delete:
            self._delete(data)

    def _move_to_old_same_fs(self, src: Path, old_dir: Path) -> None:
        """
        Перемещает файл src в old_dir/src.path.
        Если src исчез — молча выходим.
        """
        dst = old_dir / src.name

        try:
            src.replace(dst)
        except FileNotFoundError:
            pass

    @staticmethod
    def _assert_same_fs(src: Path, old_dir: Path) -> None:
        # Проверить один и тот же диск (C:, D: ...)
        if src.resolve().drive.lower() != old_dir.resolve().drive.lower():
            raise ValueError(
                f"OLD должен быть на том же диске, что и репозиторий: "
                f"OLD - {old_dir.resolve().drive} и репозиторий - {src.resolve().drive}"
            )

    def _download(self, data: TransferInput):
        ftp = Ftp(FTPInput(data.context, data.ftp))
        snapshots = data.snapshots

        new_dir = data.context.app.new_dir_path
        self.safe_mkdir(new_dir)
        old_dir = data.context.app.old_dir_path
        self.safe_mkdir(old_dir)

        snapshots_by_name: dict[str, FileSnapshot] = {
            Path(snap.path).name: snap for snap in snapshots
        }

        self.sanitize_new_dir(new_dir=new_dir, snapshots_by_name=snapshots_by_name)
        valid_new_snapshots = self.ensure_new_dir_ready(
            new_dir=new_dir, old_dir=old_dir, snapshots_by_name=snapshots_by_name
        )

        valid_names = {s.path for s in valid_new_snapshots}
        snapshots_to_download = {s for s in snapshots if s.path not in valid_names}
        # snapshots_to_download = self.apply_stop_set(data, snapshots_to_download)
        # snapshots_to_download = self.apply_add_set(data, snapshots_to_download)
        ### !!!!! - STOP LIST + ADD LIST - !!!!! ### - добавить
        for snapshot in snapshots_to_download:
            remote_full = snapshot.path
            local_name = Path(remote_full).name
            local_full_path = new_dir / local_name

            try:
                ftp.download_file(
                    remote_full_item=FTPDirItem(
                        remote_full=remote_full,
                        size=snapshot.size,
                        md5_hash=snapshot.md5_hash,
                    ),
                    local_full_path=local_full_path,
                    local_file_size=self.get_local_file_size(local_full_path),
                )
            except DownloadFileError as e:
                import traceback

                traceback.print_exc()
                logger.error(
                    "Файл {file} не загружен в директорию {dir}",
                    file=remote_full,
                    dir=new_dir,
                )

    def _delete(self, data: TransferInput):
        local_dir = data.context.app.local_dir
        self.safe_mkdir(local_dir)

        old_dir = data.context.app.old_dir_path
        self.safe_mkdir(old_dir)

        snapshots = data.snapshots

        self._assert_same_fs(local_dir, old_dir)

        for snapshot in snapshots:
            file_path = Path(local_dir) / snapshot.path
            try:
                self._move_to_old_same_fs(src=file_path, old_dir=old_dir)
            except (
                FileNotFoundError,
                PermissionError,
                OSError,
            ) as e:
                raise RuntimeError(
                    f"Не смог переместить файл {e} из {file_path} в {old_dir}"
                ) from e
        return

    def safe_mkdir(self, dir_path: Path) -> None:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    def sanitize_new_dir(
        self, new_dir: Path, snapshots_by_name: dict[str, FileSnapshot]
    ) -> None:
        for path in new_dir.iterdir():
            self._ensure_is_file_or_exit(new_dir=new_dir, path=path)
            snap = snapshots_by_name.get(path.name)

            if self._delete_if_unknown(new_dir=new_dir, path=path, snap=snap):
                continue

            self._delete_if_oversized_or_size_zero(
                new_dir=new_dir, path=path, snap=snap
            )

    def _ensure_is_file_or_exit(self, new_dir: Path, path: Path) -> None:
        if path.is_file():
            return

        logger.error(
            "В директории {dir} найден не-файл: {item_in_dir}. Программа прекращает работу.",
            dir=new_dir,
            item_in_dir=path,
        )
        raise SystemExit(1)

    def _delete_if_unknown(
        self, new_dir: Path, path: Path, snap: FileSnapshot | None
    ) -> bool:
        if snap is not None:
            return False

        logger.warning(
            "Обнаружен не запланированный к загрузке файл {item_in_dir} — файл будет удалён.",
            item_in_dir=path,
        )
        try:
            path.unlink(missing_ok=True)
        except PermissionError as e:
            logger.error("Не смог удалить файл {path}:\n{e}", path=path, e=e)
            return False
        return True

    def _delete_if_oversized_or_size_zero(
        self, new_dir: Path, path: Path, snap: FileSnapshot | None
    ) -> None:

        local_size = self.get_local_file_size(path)
        remote_size = snap.size if snap is not None else 0

        if (
            remote_size is None
            or remote_size == 0
            or local_size > remote_size
            or local_size == 0
        ):
            logger.warning(
                "В директории {new_dir} размер файла {name} ({local}) равен 0\n"
                "или больше размера на FTP ({remote}) или размер файла на FTP неизвестен\n"
                "файл {name} будет удалён.\n",
                new_dir=new_dir,
                name=path.name,
                local=local_size,
                remote=remote_size or 0,
            )
            path.unlink(missing_ok=True)

    def ensure_new_dir_ready(
        self,
        *,
        new_dir: Path,
        old_dir: Path,
        snapshots_by_name: dict[str, FileSnapshot],
    ) -> list[FileSnapshot]:
        """
        Если NEW пуста — просто строим локальный снапшот.
        Если NEW не пуста — спрашиваем пользователя: продолжить / начать заново / остановить.
        Возвращает то же, что items_dir_to_filesnapshots().
        """
        items_dir = list(new_dir.iterdir())
        if not items_dir:
            return self.select_size_matched_snapshots(
                items_dir=items_dir,
                snapshots_by_name=snapshots_by_name,
            )

        logger.info(
            "В директории {new_dir} обнаружены компоненты системы", new_dir=new_dir
        )

        action = self._prompt_new_dir_action()

        if action is NewDirAction.STOP:
            logger.error("Пользователь отказался продолжать работу")
            raise SystemExit(1)

        if action is NewDirAction.RESTART:
            self.clean_dir(new_dir)
            self.clean_dir(old_dir)
            items_dir = list(new_dir.iterdir())

        # CONTINUE или RESTART -> строим снапшот по текущему содержимому NEW
        print("Продолжаем работать")
        return self.select_size_matched_snapshots(
            items_dir=items_dir,
            snapshots_by_name=snapshots_by_name,
        )

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

    def select_size_matched_snapshots(
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
