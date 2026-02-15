# Все сервисы контроллера реализуют use-case контракт:
#   run(input) -> output

from typing import Protocol

from SYNC_APP.APP.types import ExecutionChoice
from SYNC_APP.APP.dto import (
    RuntimeContext,
    DiffPlan,
    SnapshotInput,
    DiffInput,
    TransferInput,
    ValidateInput,
    ValidateRepositoryInput,
    RepositorySnapshot,
    ReportItems,
    ReportItemInput,
    SaveInput,
)


# ---------- execution policy ----------
class ExecutionGate(Protocol):
    def check(self, ctx: RuntimeContext) -> ExecutionChoice: ...
    def record_run(self, ctx: RuntimeContext) -> None: ...


# ---------- snapshot ----------
class SnapshotService(Protocol):
    def local(self, data: SnapshotInput) -> RepositorySnapshot: ...

    def remote(self, data: SnapshotInput) -> RepositorySnapshot: ...


# ---------- diff ----------
class DiffPlanner(Protocol):
    def run(self, data: DiffInput) -> tuple[DiffPlan, bool, ReportItems]: ...


# ---------- transfer ----------
class TransferService(Protocol):
    def run(self, data: TransferInput) -> tuple[bool, ReportItems]: ...


# ---------- Сверка скаченных файлов с эталоном и, при необходимости, перенос файлов
class ValidateService(Protocol):
    def run(self, data: ValidateInput) -> tuple[bool, ReportItems]: ...


class SaveService(Protocol):
    def commit_keep_new_old_dirs(self, data: SaveInput) -> ReportItems: ...


# ---------- Вывод сводного отчёта
class ReportService(Protocol):
    def run(self, data: ReportItemInput) -> None: ...


# ---------- validator ----------
class RepositoryValidator(Protocol):
    def run(self, data: ValidateRepositoryInput) -> ReportItems: ...
