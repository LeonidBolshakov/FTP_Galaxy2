# Все сервисы контроллера реализуют use-case контракт:
#   run(input) -> output

from typing import Protocol

from SRC.SYNC_APP.app.dto import (
    RuntimeContext,
    DiffPlan,
    RepositorySnapshot,
    SnapshotMode,
    ExecutionChoice,
    DiffInput,
    TransferInput,
    ErrorEvent,
    VersionConflictGroup,
)


# ---------- execution policy ----------
class ExecutionPolicy(Protocol):
    def run(self, ctx: RuntimeContext) -> ExecutionChoice: ...


# ---------- snapshot ----------
class SnapshotService(Protocol):
    def run(self, mode: SnapshotMode) -> RepositorySnapshot: ...


# ---------- diff ----------
class DiffPlanner(Protocol):
    def run(self, data: DiffInput) -> DiffPlan: ...


# ---------- transfer ----------
class TransferService(Protocol):
    def run(self, data: TransferInput) -> None: ...


# ---------- validator ----------
class RepositoryValidator(Protocol):
    def run(self, snapshot: RepositorySnapshot) -> list[VersionConflictGroup]: ...


# ---------- errors ----------
class ErrorHandler(Protocol):
    def run(self, event: ErrorEvent) -> None: ...
