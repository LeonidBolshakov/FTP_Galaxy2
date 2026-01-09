from pathlib import Path, PurePosixPath
from enum import Enum, auto
import os
import sys
import shutil
import tempfile
from typing import Callable

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

    def _safe_copy(self, src: Path, dst: Path) -> None:
        if not src.exists():
            return

        fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", dir=dst.parent)
        tmp = Path(tmp_name)
        os.close(fd)
        try:
            shutil.copy2(src, tmp)
            tmp.replace(dst)

        except FileNotFoundError:
            if not src.exists():  # race: src мог исчезнуть
                return
            raise  # скорее всего ошибка в dst

        except Exception:
            tmp.unlink()
            raise

    def _safe_move(self, src: Path, dst: Path) -> None:
        try:
            src.replace(dst)
        except FileNotFoundError:
            if not src.exists():  # race: src мог исчезнуть
                return
            raise  # скорее всего ошибка в dst

    @staticmethod
    def _assert_same_fs(src: Path, old_dir: Path) -> None:
        # Проверить один и тот же диск (C:, D: ...)
        if src.resolve().drive.lower() != old_dir.resolve().drive.lower():
            raise ValueError(
                f"OLD должен быть на том же диске, что и репозиторий: "
                f"OLD - {old_dir.resolve().drive} и репозиторий - {src.resolve().drive}"
            )

    def _download(self, data: TransferInput) -> None:
        ftp = Ftp(FTPInput(data.context, data.ftp))
        snapshots = data.snapshots

        local_dir, new_dir, old_dir = self._prepare_official_dirs(data)

        snapshots_by_name = self._index_snapshots_by_name(snapshots)

        self._sanitize_new_dir(new_dir=new_dir, snapshots_by_name=snapshots_by_name)
        valid_new_snapshots = self._ensure_new_dir_ready(
            new_dir=new_dir,
            old_dir=old_dir,
            snapshots_by_name=snapshots_by_name,
        )

        snapshots_to_download = self._select_snapshots_to_download(
            snapshots, valid_new_snapshots
        )

        self._download_snapshot_files(ftp, snapshots_to_download, new_dir)

        self._copy_local_files(
            snapshots=snapshots_to_download,
            from_dir=new_dir,
            to_dir=local_dir,
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
        # Для FTP-путей безопаснее PurePosixPath (если там "/"), чем Path на Windows
        return {self._snapshot_name(snap): snap for snap in snapshots}

    # --- 3) Определение, что ещё нужно скачать
    def _select_snapshots_to_download(
            self,
            snapshots: list[FileSnapshot],
            valid_new_snapshots: list[FileSnapshot],
    ) -> list[FileSnapshot]:
        valid_paths = {s.path for s in valid_new_snapshots}
        return [s for s in snapshots if s.path not in valid_paths]

    # --- 4) Загрузка файлов
    def _download_snapshot_files(
            self, ftp: Ftp, snapshots_to_download: list[FileSnapshot], new_dir: Path
    ) -> None:
        if snapshots_to_download:
            print("Начинаем загрузку файлов")

        for snapshot in snapshots_to_download:
            self._download_one_snapshot(ftp, snapshot, new_dir)

    # --- 5) Скачивание одного файла
    def _download_one_snapshot(
            self, ftp: Ftp, snapshot: FileSnapshot, new_dir: Path
    ) -> None:
        remote_full = snapshot.path
        # local_name = self._snapshot_name(remote_full)
        local_name = self._snapshot_name(snapshot)
        local_full_path = new_dir / local_name

        try:
            ftp.download_file(
                remote_full_item=self._ftp_item_from_snapshot(snapshot),
                local_full_path=local_full_path,
                local_file_size=self.get_local_file_size(local_full_path),
            )
        except DownloadFileError as e:
            try:
                local_full_path.unlink(missing_ok=True)
            except Exception:
                pass
            logger.error(
                "Файл {file} не загружен в директорию {dir}\n{e}",
                file=remote_full,
                dir=new_dir,
                e=e,
            )

    # --- 6) Построение FTPDirItem из снапшота
    def _ftp_item_from_snapshot(self, snapshot: FileSnapshot) -> FTPDirItem:
        return FTPDirItem(
            remote_full=snapshot.path,
            size=snapshot.size,
            md5_hash=snapshot.md5_hash,
        )

    def _delete(self, data: TransferInput):

        local_dir, _, old_dir = self._prepare_official_dirs(data)

        self._move_local_files(
            snapshots=data.snapshots,
            from_dir=local_dir,
            to_dir=old_dir,
        )

    def safe_mkdir(self, dir_path: Path) -> None:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    def _sanitize_new_dir(
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

    def _ensure_new_dir_ready(
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

    def _copy_local_files(
            self,
            snapshots: list[FileSnapshot],
            from_dir: Path,
            to_dir: Path,
    ) -> None:

        self._help_copy_or_move(
            callback=self._safe_copy,
            snapshots=snapshots,
            from_dir=from_dir,
            to_dir=to_dir,
        )

    def _move_local_files(
            self,
            snapshots: list[FileSnapshot],
            from_dir: Path,
            to_dir: Path,
    ) -> None:

        self._assert_same_fs(from_dir, to_dir)

        self._help_copy_or_move(
            callback=self._safe_move,
            snapshots=snapshots,
            from_dir=from_dir,
            to_dir=to_dir,
        )

    def _help_copy_or_move(
            self,
            callback: Callable[[Path, Path], None],
            snapshots: list[FileSnapshot],
            from_dir: Path,
            to_dir: Path,
    ) -> None:
        for snapshot in snapshots:
            from_path = Path(from_dir) / self._snapshot_name(snapshot)
            to_path = Path(to_dir) / self._snapshot_name(snapshot)
            try:
                callback(from_path, to_path)
            except (
                    FileNotFoundError,
                    PermissionError,
                    OSError,
            ) as e:
                raise RuntimeError(
                    f"Не смог переместить файл из {from_path} в {to_dir}\n{e}"
                ) from e
        return

    def _snapshot_name(self, snap: FileSnapshot) -> str:
        return PurePosixPath(snap.path).name
