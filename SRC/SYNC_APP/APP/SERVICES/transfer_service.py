from pathlib import Path

from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    TransferInput,
    TransferMode,
    FTPInput,
    FTPDirItem,
    FileSnapshot,
)
from SRC.SYNC_APP.ADAPTERS.ftp import Ftp


class TransferService:
    def run(self, data: TransferInput) -> None:

        mode = data.mode
        if mode == TransferMode.download:
            self._download(data)
        elif mode == TransferMode.delete:
            self._delete(data)

    def _move_to_old_same_fs(self, src: Path, old_dir: Path) -> None:
        """
        Перемещает файл src в old_dir/src.name.
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
                f"OLD должен быть на том же диске, что и src: "
                f"{old_dir.resolve().drive} и {src.resolve().drive}"
            )

    def _download(self, data: TransferInput):
        ftp = Ftp(FTPInput(data.context, data.ftp))
        snapshots = data.snapshots

        new_dir = data.context.app.new_dir_path
        self.safe_mkdir(new_dir)

        try:
            new_dir_list = self.normalize_new(
                snapshots=snapshots,
                new_dir=new_dir,
                old_dir=data.context.app.old_dir_path,
            )
        except SystemExit:
            raise

        snapsots_wuthout_new_list = list(set(snapshots) - set(new_dir_list))
        for snapshot in snapsots_wuthout_new_list:
            remote_full = snapshot.name
            local_name = Path(remote_full).name
            local_full_path = new_dir / local_name

            ftp.download_file(
                remote_full_item=FTPDirItem(
                    remote_full=remote_full,
                    size=snapshot.size,
                    md5_hash=snapshot.md5_hash,
                ),
                local_full_path=local_full_path,
            )

    #         self._download_missing_files_to_new_dir(
    #             ftp=ftp,
    #             snapsots_wuthout_new_list=snapsots_wuthout_new_list,
    #             new_dir=new_dir,
    #         )
    #     return
    #
    # def _download_missing_files_to_new_dir(
    #     self,
    #     ftp: Ftp,
    #     snapsots_wuthout_new_list: list[FileSnapshot],
    #     new_dir: Path,
    # ) -> None:
    #     for snapshot in snapsots_wuthout_new_list:
    #         remote_full = snapshot.name
    #         local_name = Path(remote_full).name
    #         local_full_path = new_dir / local_name
    #
    #         ftp.download_file(
    #             remote_full_item=FTPDirItem(
    #                 remote_full=remote_full,
    #                 size=snapshot.size,
    #                 md5_hash=snapshot.md5_hash,
    #             ),
    #             local_full_path=local_full_path,
    #         )

    def _delete(self, data: TransferInput):
        local_dir = data.context.app.local_dir
        self.safe_mkdir(local_dir)
        old_dir = data.context.app.old_dir_path
        self.safe_mkdir(old_dir)
        snapshots = data.snapshots
        self._assert_same_fs(local_dir, old_dir)
        for snapshot in snapshots:
            file_path = Path(local_dir) / snapshot.name
            try:
                self._move_to_old_same_fs(src=file_path, old_dir=old_dir)
            except (
                    FileNotFoundError,
                    PermissionError,
                    OSError,
            ) as e:
                raise RuntimeError(f"Не смог удалить файл {e}") from e
        return

    def safe_mkdir(self, dir_path: Path) -> None:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    def normalize_new(
            self, snapshots: list[FileSnapshot], new_dir: Path, old_dir: Path
    ) -> list[FileSnapshot]:

        snapshots_by_name: dict[str, FileSnapshot] = {
            Path(s.name).name: s for s in snapshots
        }
        log = logger.bind(dir=str(new_dir))

        for item_in_dir in new_dir.iterdir():
            if not item_in_dir.is_file():
                log.error(
                    "В директории найден не-файл: {item_in_dir}. Программа прекращает работу.",
                    item_in_dir=item_in_dir,
                )
                raise SystemExit(1)

            snap = snapshots_by_name.get(item_in_dir.name)

            if snap is None:
                log.warning(
                    "Обнаружен неизвыестный файл {item_in_dir} — \n"
                    "файл будет удалён.",
                    item_in_dir=item_in_dir,
                )
                item_in_dir.unlink(missing_ok=True)
                continue

            local_size = item_in_dir.stat().st_size
            if local_size != snap.size:
                log.warning(
                    "Размер файла {name} ({local}) не равен размеру на FTP ({remote}) —\n"
                    "файл будет удалён.",
                    name=item_in_dir.name,
                    local=local_size,
                    remote=snap.size,
                )
                item_in_dir.unlink(missing_ok=True)

        items_dir = []
        for item_dir in new_dir.iterdir():
            items_dir.append(item_dir)

        if items_dir:
            logger.info(f"В директории {new_dir} обнаружены компоненты системы")
            while True:
                respon = input(
                    "Директория NEW содержит компоненты системы.\n"
                    "Продолжаем скачивание? - 'П' + Enter\n"
                    "Начинаем новое скачиывние? \n"
                    "Компоненты будут удалены в каталогах NEW и OLD? - 'Н' + Enter\n"
                    "Прекращаем работу - 'С' + Enter\n"
                )
                if respon in {"П", "п", "G", "g"}:
                    return self.items_dir_to_filesnapshots(
                        items_dir=items_dir, snapshots_by_name=snapshots_by_name
                    )

                if respon in {"Н", "н", "Y", "y"}:
                    self.clean_dir(new_dir)
                    self.clean_dir(old_dir)
                    return self.items_dir_to_filesnapshots(
                        items_dir=items_dir, snapshots_by_name=snapshots_by_name
                    )

                if respon in {"С", "с", "C", "c"}:
                    logger.error("Пользователь отказался продолжать работу")
                    raise SystemExit(1)

        return self.items_dir_to_filesnapshots(
            items_dir=items_dir, snapshots_by_name=snapshots_by_name
        )

    def items_dir_to_filesnapshots(
            self, items_dir, snapshots_by_name
    ) -> list[FileSnapshot]:
        file_snapshots: list[FileSnapshot] = []
        for item_dir in items_dir:
            file_snapshot = snapshots_by_name[item_dir.name]
            file_snapshots.append(file_snapshot)

        return file_snapshots

    def clean_dir(self, dir_path: Path) -> None:
        for p in dir_path.iterdir():
            p.unlink(missing_ok=True)
