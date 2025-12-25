# stubs.py
from loguru import logger

from SRC.SYNC_APP.app.dto import (
    RuntimeContext,
    RepositorySnapshot,
    SnapshotMode,
    DiffInput,
    DiffPlan,
    TransferInput,
    ErrorEvent,
    ExecutionChoice,
)


class AlwaysRunPolicy:
    def run(self, ctx: RuntimeContext) -> ExecutionChoice:
        return ExecutionChoice.RUN


class EmptySnapshotService:
    def run(self, mode: SnapshotMode) -> RepositorySnapshot:
        logger.debug("Snapshot mode: {}", mode)
        return RepositorySnapshot(files={})


class EmptyDiffPlanner:
    def run(self, data: DiffInput) -> DiffPlan:
        return DiffPlan(to_delete=[], to_download=[], diff_files=[])


class TransferService:
    def run(self, data: TransferInput) -> None:
        logger.info("Transfer {}: {} file(s)", data.mode, len(data.paths))


class LogErrorHandler:
    def run(self, event: ErrorEvent) -> None:
        logger.error("Error {}: {}", event.code, event.details)
