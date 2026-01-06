# Все сервисы контроллера реализуют use-case контракт:
#   run(input) -> output

from typing import Protocol

from SRC.SYNC_APP.APP.dto import (
    RuntimeContext,
    DiffPlan,
    RepositorySnapshot,
    SnapshotInput,
    ExecutionChoice,
    DiffInput,
    TransferInput,
    ErrorEvent,
    VersionConflictGroup,
    ValidateRepositoryInput,
    RepositorySnapshot,
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


# ---------- validator ----------
class RepositoryValidator(Protocol):
    def run(self, data: ValidateRepositoryInput) -> list[VersionConflictGroup]: ...


# ---------- errors ----------
class ErrorHandler(Protocol):
    def run(self, event: ErrorEvent) -> None: ...
