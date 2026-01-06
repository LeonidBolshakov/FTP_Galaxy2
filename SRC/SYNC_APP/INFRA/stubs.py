# stubs.py
from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    RepositorySnapshot,
    DiffInput,
    DiffPlan,
    TransferInput,
    ErrorEvent,
    SnapshotInput,
    ValidateRepositoryInput,
)


class EmptySnapshotService:
    def local(self, data: SnapshotInput) -> RepositorySnapshot:
        logger.debug("Snapshot mode: local")
        return RepositorySnapshot(files={})

    def remote(self, data: SnapshotInput) -> RepositorySnapshot:
        logger.debug("Snapshot mode: remote")
        return RepositorySnapshot(files={})


class EmptyDiffPlanner:
    def run(self, data: DiffInput) -> DiffPlan:
        return DiffPlan(to_delete=[], to_download=[], diff_files=[])


class TransferService:
    def run(self, data: TransferInput) -> None:
        logger.info("Transfer {}: {} file(s)", data.mode, len(data.snapshots))


class EmptyRepositoryValidator:
    def run(self, data: ValidateRepositoryInput):
        logger.info(f"Validating repository {data.snapshot}")


class LogErrorHandler:
    def run(self, event: ErrorEvent) -> None:
        logger.error("Error {}: {}", event.code, event.details)
