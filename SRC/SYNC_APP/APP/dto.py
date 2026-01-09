from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Set
from ftplib import FTP

from SRC.SYNC_APP.CONFIG.config import AppConfig


class ConnectError(Exception):
    pass


class DownloadFileError(Exception):
    pass


class DownloadDirError(Exception):
    pass


class FTPListError(Exception):
    pass


class RepositorySnapshotError(Exception):
    pass


class LocalFileAccessError(RuntimeError):
    pass


# fmt: off
@dataclass(frozen=True)
class RuntimeContext:
    app                 : AppConfig
    once_per_day        : bool
    use_stop_list       : bool


@dataclass(frozen=True)
class InvalidFile:
    path                    : str
    error                   : str

@dataclass(frozen=True)
class DiffPlan:
    to_delete               : list[FileSnapshot]
    to_download             : list[FileSnapshot]
    diff_files              : list[InvalidFile]


class ModeSnapShop(Enum):
    LITE_MODE               = auto()
    FULL_MODE               = auto()

class ModeDiffPlan(Enum):
    USE_STOP_LIST           = auto()
    NOT_USE_STOP_LIST       = auto()


@dataclass(frozen=True)
class FileSnapshot:
    path                    : str
    size                    : int | None
    md5_hash                : str | None

    def _k(self) -> str:
        return self.path.strip()

    def __hash__(self) -> int:
        return hash(self._k())

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FileSnapshot) and self._k() == other._k()


@dataclass(frozen=True)
class RepositorySnapshot:
    files               : dict[str, FileSnapshot]


class ErrorNumber(Enum):
    diff_pre_files      = auto()
    diff_download_files = auto()
    conflict_files      = auto()


class TransferMode(Enum):
    delete              = auto()
    download            = auto()


class ExecutionChoice(Enum):
    RUN                 = auto()
    SKIP                = auto()


@dataclass(frozen=True)
class SnapshotInput:
    context             : RuntimeContext
    ftp                 : FTP
    mode                : ModeSnapShop
    only_for            : Set | None = None


@dataclass(frozen=True)
class DiffInput:
    context             : RuntimeContext
    local               : RepositorySnapshot
    remote              : RepositorySnapshot
    use_stop_list       : ModeDiffPlan


@dataclass(frozen=True)
class TransferInput:
    context             : RuntimeContext
    ftp                 : FTP
    mode                : TransferMode
    snapshots           : list[FileSnapshot]


@dataclass(frozen=True)
class ErrorEvent:
    context             : RuntimeContext
    code                : ErrorNumber
    details             : object


@dataclass(frozen=True)
class VersionConflictGroup:
    latest              : str
    older               : list[str]


@dataclass(frozen=True)
class ValidateRepositoryInput:
    context             : RuntimeContext
    snapshot            : RepositorySnapshot


@dataclass(frozen=True)
class FTPInput:
    context             : RuntimeContext
    ftp                 : FTP


@dataclass(frozen=True)
class FTPDirItem:
    remote_full         : str
    size                : int | None
    md5_hash            : str | None


@dataclass(frozen=True)
class DownloadDirFtpInput:
    with_md5            : ModeSnapShop          = ModeSnapShop.LITE_MODE
    only_for            : Set[str] | None       = None

# fmt: on
    def __post_init__(self):
        if self.only_for and not self.with_md5:
            raise ValueError("only_for допустим только при with_md5=True")

    def __repr__(self) -> str:
        if self.only_for is None:
            only_for_repr = "None"
        else:
            only_for_repr = f"{len(self.only_for)} files"

        return (
            f"{self.__class__.__name__}("
            f"with_md5={self.with_md5}, "
            f"only_for={only_for_repr}"
            f")"
        )
