from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Set, TypeAlias, Protocol
from ftplib import FTP
from pathlib import Path

from SRC.SYNC_APP.CONFIG.config import AppConfig

ReportItems: TypeAlias = list["ReportItem"]


class ConnectError(Exception):
    pass


class DownloadFileError(Exception):
    pass


class DownloadDirError(Exception):
    pass


class ConfigError(Exception):
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
class DiffPlan:
    to_delete           : list[FileSnapshot]
    to_download         : list[FileSnapshot]
    report_plan         : ReportItems


class ModeSnapshot(Enum):
    LITE_MODE           = auto()
    FULL_MODE           = auto()

class ModeDiffPlan(Enum):
    USE_STOP_LIST       = auto()
    NOT_USE_STOP_LIST   = auto()


@dataclass(frozen=True)
class FileSnapshot:
    name                : str
    size                : int | None
    md5_hash            : str | None

    def _k(self) -> str:
        return self.name.strip()

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


class ExecutionChoice(Enum):
    RUN                 = auto()
    SKIP                = auto()


@dataclass(frozen=True)
class SnapshotInput:
    context             : RuntimeContext
    mode                : ModeSnapshot
    ftp                 : Ftp | None = None
    only_for            : Set[str] | None = None


@dataclass(frozen=True)
class ReportItem:
    name                : str
    comment             : str


@dataclass(frozen=True)
class ValidateInput:
    context             : RuntimeContext
    local               : RepositorySnapshot
    remote              : RepositorySnapshot
    delete              : list[FileSnapshot]


@dataclass(frozen=True)
class DiffInput:
    context             : RuntimeContext
    local               : RepositorySnapshot
    remote              : RepositorySnapshot
    stop_list_mode      : ModeDiffPlan


@dataclass(frozen=True)
class TransferInput:
    context             : RuntimeContext
    ftp                 : Ftp
    snapshots           : list[FileSnapshot]


@dataclass(frozen=True)
class ValidateRepositoryInput:
    context             : RuntimeContext
    snapshot            : RepositorySnapshot


@dataclass(frozen=True)
class FTPInput:
    context             : RuntimeContext
    ftp                 : FTP


@dataclass(frozen=True)
class ReportItemInput:
    context             : RuntimeContext
    is_validate_commit  : bool
    report              : ReportItems


# ---------- FTP adapter ----------
class Ftp(Protocol):
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def download_dir(self, data: DownloadDirFtpInput) -> RepositorySnapshot: ...
    def download_file(
            self, remote_item: FileSnapshot, local_full_path: Path) -> None: ...


@dataclass(frozen=True)
class DownloadDirFtpInput:
    hash_mode           : ModeSnapshot          = ModeSnapshot.LITE_MODE
    only_for            : Set[str] | None       = None

# fmt: on
    def __repr__(self) -> str:
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
