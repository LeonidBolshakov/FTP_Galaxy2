# Все сервисы контроллера реализуют use-case контракт:
#   run(input) -> output

from typing import Protocol

from SRC.SYNC_APP.APP.dto import (
    RuntimeContext,
    DiffPlan,
    SnapshotInput,
    ExecutionChoice,
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
    def run(self, data: DiffInput) -> DiffPlan: ...


# ---------- transfer ----------
class TransferService(Protocol):
    def run(self, data: TransferInput) -> None: ...


# ---------- Сверка скаченных файлов с эталоном и, при необходимости, перенос файлов
class ValidateService(Protocol):
    def run(self, data: ValidateInput) -> ReportItems: ...


class SaveService(Protocol):
    def commit_keep_new_old_files(self, data: SaveInput) -> None: ...


# ---------- Вывод сводного отчёта
class ReportService(Protocol):
    def run(self, data: ReportItemInput) -> None: ...


# ---------- validator ----------
class RepositoryValidator(Protocol):
    def run(self, data: ValidateRepositoryInput) -> ReportItems: ...
