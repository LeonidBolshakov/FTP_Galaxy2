from pathlib import Path
from enum import Enum, auto
from typing import assert_never, Callable
import uuid
import shutil

from loguru import logger

from SYNC_APP.APP.dto import (
    SaveInput,
    FileSnapshot,
    ReportItems,
    ReportItem,
    StatusReport,
)
from GENERAL.errors import ConfigError, LocalFileAccessError, UserAbend
from SYNC_APP.INFRA.utils import (
    prompt_action,
    clean_dir,
    sure_same_drive,
    safe_mkdir,
)

MENU = (
    "[У] - Удалить содержимое директории OLD",
    "[П] - Удалить содержимое директории OLD, я самостоятельно сохранил данные",
    "[С] - Стоп. Остановить работу",
)


# fmt: off
class OldDirAction(Enum):
    DELETE                      = auto()    # Удалить содержимое директории OLD
    CONTINUE                    = auto()    # Продолжить работу
    STOP                        = auto()    # Выходим из программы

MAPPING = {
    "у": OldDirAction.DELETE,       "e": OldDirAction.DELETE,   "u": OldDirAction.DELETE,
    "п": OldDirAction.CONTINUE,     "g": OldDirAction.CONTINUE, "p": OldDirAction.CONTINUE,
    "с": OldDirAction.STOP,         "c": OldDirAction.STOP,     "s": OldDirAction.STOP,
}
# fmt: on


OldDirSelector = Callable[[Path], OldDirAction]


def interactive_old_dir_selector(_: Path) -> OldDirAction:
    return prompt_action(menu=MENU, mapping=MAPPING)


class SaveService:
    def __init__(self, old_dir_selector: OldDirSelector | None = None):
        self._old_dir_selector = old_dir_selector or interactive_old_dir_selector

    def commit_keep_new_old_dirs(self, data: SaveInput) -> ReportItems:

        local_dir = self._get_parameter(param="local_dir", data=data)
        new_dir = self._get_parameter(param="new_dir", data=data)
        old_dir = self._get_parameter(param="old_dir", data=data)
        report: ReportItems = []

        count_old_files = self._move_files(
            list_files=data.delete,
            from_dir=local_dir,
            to_dir=old_dir,
        )
        if count_old_files != 0:
            report.append(
                ReportItem(
                    name="",
                    status=StatusReport.INFO,
                    comment=f"В директорию OLD перемещено {count_old_files} не соответсвующих эталону версий компонент",
                )
            )

        count_new_files = self._copy_files(
            from_dir=new_dir,
            to_dir=local_dir,
        )
        if count_new_files != 0:
            report.append(
                ReportItem(
                    name="",
                    status=StatusReport.INFO,
                    comment=f"Из директории NEW в основную директорию перемещено {count_new_files} файла/файлов",
                )
            )

        return report

    def _move_files(
            self, list_files: list[FileSnapshot], from_dir: Path, to_dir: Path
    ) -> int:
        sure_same_drive(from_dir, to_dir)
        self.sure_empty_directory(to_dir)
        return self._replace_files(list_files, from_dir, to_dir)

    def _copy_files(self, from_dir: Path, to_dir: Path) -> int:
        count_files = 0
        for file_name in from_dir.iterdir():
            self._safe_copy_file(
                from_full_path=file_name, to_full_path=to_dir / file_name.name
            )
            count_files += 1
        return count_files

    def sure_empty_directory(self, to_dir: Path) -> None:
        safe_mkdir(to_dir)
        if any(to_dir.iterdir()):
            action = self._old_dir_selector(to_dir)
            match action:
                case OldDirAction.DELETE:
                    logger.info("Пользователь выбрал вариант удаления содержимого OLD")
                    clean_dir(to_dir)

                case OldDirAction.CONTINUE:
                    logger.info(
                        "Пользователь сам сохранил OLD и выбрал вариант удаления содержимого OLD"
                    )
                    clean_dir(to_dir)

                case OldDirAction.STOP:
                    raise UserAbend(
                        "Директория OLD не пуста. Пользователь принял решени прекратить работу"
                    )

                case _:
                    assert_never(action)

    def _replace_files(
            self, list_file_snaps: list[FileSnapshot], from_dir: Path, to_dir: Path
    ) -> int:

        count_files = 0
        for file in list_file_snaps:
            count_files += 1
            self._replace_file(
                file_full_path=from_dir / file.name, target_full_path=to_dir / file.name
            )

        return count_files

    def _replace_file(self, file_full_path: Path, target_full_path: Path) -> None:
        self._enshure_is_file(file_full_path)
        try:
            file_full_path.replace(target_full_path)
        except PermissionError:
            raise LocalFileAccessError(f"Нет доступа к файлу {file_full_path}")

    def _safe_copy_file(self, from_full_path: Path, to_full_path: Path) -> None:
        self._enshure_is_file(from_full_path)
        safe_mkdir(to_full_path.parent)

        tmp: Path | None = None
        try:
            tmp = to_full_path.with_name(f".tmp-{uuid.uuid4().hex}-{to_full_path.name}")
            shutil.copy2(from_full_path, tmp)
            tmp.replace(to_full_path)  # атомарно в пределах ФС назначения
        except PermissionError:
            raise LocalFileAccessError(f"Нет доступа к {to_full_path} или {tmp}")
        finally:
            if tmp is not None and tmp.exists():
                try:
                    tmp.unlink(missing_ok=True)
                except PermissionError:
                    raise LocalFileAccessError(f"Нет доступа к {tmp}")

    @staticmethod
    def _copy_file_to_temp(file_full_path: Path) -> Path:
        dir_file = file_full_path.parent
        temp_full_name = dir_file / uuid.uuid4().hex
        shutil.copy2(file_full_path, temp_full_name)
        return temp_full_name

    @staticmethod
    def _get_parameter(param: str, data: SaveInput) -> Path:
        attr = getattr(data.context.app, param, None)
        if attr is None:
            raise ConfigError(f"Не задан параметр {param}")

        return Path(attr)

    @staticmethod
    def _enshure_is_file(path: Path) -> None:
        if not path.is_file():
            raise LocalFileAccessError(
                f"Ошибка в списке компонент репозитория. Это не файл или файл отсутсвует.\n"
                f"{path.name}"
            )
