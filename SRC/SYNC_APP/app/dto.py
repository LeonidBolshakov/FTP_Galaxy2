from dataclasses import dataclass
from enum import Enum, auto

from SRC.SYNC_APP.CONFIG.config import AppConfig

# fmt: off
@dataclass(frozen=True)
class RuntimeContext:
    app                 : AppConfig
    once_per_day        : bool


@dataclass(frozen=True)
class InvalidFile:
    path                : str
    error               : str

@dataclass(frozen=True)
class DiffPlan:
    to_delete           : list[str]
    to_download         : list[str]
    diff_files          : list[InvalidFile]


@dataclass(frozen=True)
class FileSnapshot:
    size                : int
    file_hash           : str


@dataclass(frozen=True)
class RepositorySnapshot:
    files               : dict[str, FileSnapshot]

class ErrorNumber(Enum):
    diff_files          = auto()
    conflict_files      = auto()


class SnapshotMode(Enum):
    remote_lite         = auto()
    local_lite          = auto()
    remote_full         = auto()
    local_full          = auto()


class TransferMode(Enum):
    delete              = auto()
    download            = auto()


class ExecutionChoice(Enum):
    RUN                 = auto()
    SKIP                = auto()


@dataclass(frozen=True)
class DiffInput:
    remote              : RepositorySnapshot
    local               : RepositorySnapshot


@dataclass(frozen=True)
class TransferInput:
    mode                : TransferMode
    paths               : list[str]


@dataclass(frozen=True)
class ErrorEvent:
    code                : ErrorNumber
    details             : object


@dataclass(frozen=True)
class VersionConflictGroup:
    latest              : str                   # файл с максимальной версией в имени
    older               : list[str]             # файлы с меньшими версиями
# fmt: on
