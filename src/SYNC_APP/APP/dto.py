"""DTO и доменные типы для приложения синхронизации (SYNC_APP).

В модуле собраны:
— доменные исключения, которые сервисы используют для сигнализации об ошибках,
— перечисления режимов/статусов,
— "снимки" файлов/репозитория и входные структуры (Input) для сервисов,
— протокол (интерфейс) FTP-адаптера.

Важно:
— Благодаря `from __future__ import annotations` ниже можно использовать аннотации,
  ссылающиеся на классы, объявленные позднее (forward references).
— Большинство ошибок уровня файла (`DownloadFileError`) ожидаемо не "роняют" приложение,
  а позволяют пропустить проблемный файл и перейти к следующему (это зависит от того,
  как верхний уровень собирает отчёт и обрабатывает исключения).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Set, TypeAlias, Protocol
from ftplib import FTP
from pathlib import Path

from SYNC_APP.CONFIG.config import SyncConfig

ReportItems: TypeAlias = list["ReportItem"]

# fmt: off
@dataclass(frozen=True)
class RuntimeContext:
    """Контекст выполнения приложения.

    Содержит конфигурацию и параметры запуска, которые передаются в сервисы/адаптеры.

    Attributes
    ----------
    app
        Конфигурация приложения (пути, хосты, режимы и т.п.)
    once_per_day
        Ограничение на запуск "не чаще раза в день" (обрабатывается `ExecutionGate`)
    mode_stop_list
        Режим применения stop-list при построении плана различий (`ModeDiffPlan`).
    """
    app                 : SyncConfig
    once_per_day        : bool
    mode_stop_list      : ModeDiffPlan


@dataclass(frozen=True)
class DiffPlan:
    """План различий между локальным и удалённым состоянием.

    Attributes
    ----------
    to_delete
        Файлы, которые следует удалить (обычно локально), чтобы привести репозиторий к целевому виду.
    to_download
        Файлы, которые следует скачать с FTP.
    """
    to_delete           : list[FileSnapshot]
    to_download         : list[FileSnapshot]


class ModeSnapshot(Enum):
    """Режим построения снимка (snapshot)."""
    LITE_MODE           = auto()
    FULL_MODE           = auto()


class ModeDiffPlan(Enum):
    """Режим построения плана различий (diff plan) с учётом stop-list."""
    USE_STOP_LIST       = auto()
    NOT_USE_STOP_LIST   = auto()


class ValidateCommitResult(Enum):
    """Результат валидации/коммита (если используется отдельная модель результата)."""
    SUCCESS             = auto()
    FAILURE             = auto()
    UNKNOWN             = auto()


@dataclass(frozen=True)
class FileSnapshot:
    """Снимок (метаданные) одного файла.

    Notes
    -----
    Равенство и хэширование завязаны только на `name` (после `strip()`), т.е.:
    — `size` и `md5_hash` НЕ участвуют в сравнении,
    — разные представления имени с пробелами считаются одним и тем же файлом.
    """
    name                : str
    size                : int | None
    md5_hash            : str | None

    def _k(self) -> str:
        """Нормализованный ключ файла (используется для __hash__/__eq__)."""
        return self.name.strip()

    def __hash__(self) -> int:
        """Хэш по нормализованному имени файла."""
        return hash(self._k())

    def __eq__(self, other: object) -> bool:
        """Сравнение по нормализованному имени файла."""
        return isinstance(other, FileSnapshot) and self._k() == other._k()


@dataclass(frozen=True)
class RepositorySnapshot:
    """Снимок репозитория (набора файлов).

    Attributes
    ----------
    files
        Отображение: имя файла → `FileSnapshot`.
    """
    files                       : dict[str, FileSnapshot]


class ErrorNumber(Enum):
    """Идентификаторы ошибок/разделов отчёта (группировка сообщений)."""
    diff_pre_files              = auto()
    diff_download_files         = auto()
    conflict_files              = auto()


class ExecutionChoice(Enum):
    """Решение `ExecutionGate`: выполнять цикл или пропустить."""
    RUN                         = auto()
    SKIP                        = auto()


class StatusReport(Enum):
    """Уровень важности/серьёзности сообщения в отчёте."""
    INFO                        = auto()
    IMPORTANT_INFO              = auto()
    WARNING                     = auto()
    ERROR                       = auto()
    FATAL                       = auto()




@dataclass(frozen=True)
class SnapshotInput:
    """Входные данные для построения снимка (локального или удалённого).

    Attributes
    ----------
    context
        Контекст выполнения
    mode
        Режим снимка: LITE/FULL
    local_dir
        Локальная директория, если строится локальный снимок
    ftp
        FTP-адаптер, если строится удалённый снимок
    only_for
        Ограничение набора файлов (по именам), для которых нужно построить снимок.
    """
    context                     : RuntimeContext
    mode                        : ModeSnapshot
    local_dir                   : Path | None =None
    ftp                         : Ftp | None = None
    only_for                    : Set[str] | None = None


@dataclass(frozen=True)
class ReportItem:
    """Элемент отчёта о выполнении.

    Attributes
    ----------
    name
        Идентификатор/название шага или файла (как будет показано в отчёте)
    status
        Уровень сообщения (INFO/WARNING/ERROR...)
    comment
        Человеко-читаемое описание результата/ошибки.
    """
    name                        : str
    status                      : StatusReport
    comment                     : str


@dataclass(frozen=True)
class ValidCommitInput:
    """ Входные данные для _validate_commit_execution_gate """
    plan                        : DiffPlan
    new_dir                     : Path
    local_snap                  : RepositorySnapshot
    remote_snap                 : RepositorySnapshot
    delete                      : list[FileSnapshot]
    is_validate                 : bool


@dataclass(frozen=True)
class ValidateInput:
    """Входные данные для сервиса валидации результата синхронизации."""
    context                     : RuntimeContext
    plan                        : DiffPlan
    new_dir                     : Path
    local_snap                  : RepositorySnapshot
    remote_snap                 : RepositorySnapshot


@dataclass(frozen=True)
class SaveInput:
    """Входные данные для сервиса сохранения/коммита результата."""
    context                     : RuntimeContext
    delete                      : list[FileSnapshot]


@dataclass(frozen=True)
class DiffInput:
    """Входные данные для построения плана различий (diff plan)."""
    context                     : RuntimeContext
    local_snap                  : RepositorySnapshot
    remote_snap                 : RepositorySnapshot


@dataclass(frozen=True)
class TransferInput:
    """Входные данные для сервиса переноса/скачивания файлов."""
    context                     : RuntimeContext
    ftp                         : Ftp
    snapshots_for_loading       : list[FileSnapshot]


@dataclass(frozen=True)
class ValidateRepositoryInput:
    """Входные данные для дополнительных проверок репозитория после выполнения."""
    context                     : RuntimeContext
    names                       : list[str]


@dataclass(frozen=True)
class FTPInput:
    """Входные данные для инициализации FTP-адаптера."""
    context                     : RuntimeContext
    ftp                         : FTP


@dataclass(frozen=True)
class ReportItemInput:
    """Входные данные для формирования итогового отчёта."""
    context                     : RuntimeContext
    is_validate_commit          : bool
    report                      : ReportItems

# fmt: on


# ---------- FTP adapter ----------
class Ftp(Protocol):
    """Протокол (интерфейс) FTP-адаптера.

    Реальная реализация скрывает детали `ftplib` и предоставляет устойчивый API:
    — подключение/закрытие,
    — скачивание директории (получение `RepositorySnapshot`),
    — скачивание файла по `FileSnapshot` в локальный путь.
    """

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def download_dir(self, data: DownloadDirFtpInput) -> RepositorySnapshot: ...
    def download_file(self, snapshot: FileSnapshot, local_full_path: Path) -> None: ...


@dataclass(frozen=True)
class DownloadDirFtpInput:
    """Параметры скачивания/построения снимка директории на FTP.

    Attributes
    ----------
    hash_mode
        Режим снимка: LITE/FULL (влияет, например, на необходимость получать md5/size).
    only_for
        Опциональный набор имён файлов для ограниченного построения снимка.
    """

    hash_mode: ModeSnapshot = ModeSnapshot.LITE_MODE
    only_for: Set[str] | None = None

    def __repr__(self) -> str:
        """Короткое человеко-читаемое представление для логов/отладочного вывода."""
        if self.only_for is None:
            only_for_repr = "None"
        else:
            only_for_repr = f"{len(self.only_for)} files"

        return (
            f"{self.__class__.__name__}("
            f"hash_mode={self.hash_mode}, "
            f"only_for={only_for_repr} файла"
            f")"
        )
