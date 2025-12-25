from dto import (
    RuntimeContext,
    DiffPlan,
    ErrorNumber,
    SnapshotMode,
    TransferMode,
)
from ports import (
    ExecutionPolicy,
    ExecutionChoice,
    SnapshotService,
    DiffPlanner,
    DiffInput,
    TransferService,
    TransferInput,
    RepositoryValidator,
    ErrorHandler,
    ErrorEvent,
)

# fmt: off
class SyncController:
    def __init__(
        self,
        runtime_context             : RuntimeContext,
        snapshot_service            : SnapshotService,
        diff_planner                : DiffPlanner,
        transfer_service            : TransferService,
        repository_validator        : RepositoryValidator,
        error_handler               : ErrorHandler,
        execution_policy            : ExecutionPolicy,
    ):
        self.runtime_context        = runtime_context
        self.snapshot_service       = snapshot_service
        self.diff_planner           = diff_planner
        self.transfer_service       = transfer_service
        self.repository_validator   = repository_validator
        self.error_handler          = error_handler
        self.execution_policy       = execution_policy
# fmt: on

    def run(self):
        if self.runtime_context.once_per_day:
            if self.execution_policy.run(self.runtime_context) is ExecutionChoice.SKIP:
                return

        remote_lite = self.snapshot_service.run(SnapshotMode.remote_lite)
        local_lite = self.snapshot_service.run(SnapshotMode.local_lite)

        plan: DiffPlan = self.diff_planner.run(DiffInput(remote_lite, local_lite))

        self.transfer_service.run(TransferInput(TransferMode.delete, plan.to_delete))
        self.transfer_service.run(
            TransferInput(TransferMode.download, plan.to_download)
        )

        remote_full = self.snapshot_service.run(SnapshotMode.remote_full)
        local_full = self.snapshot_service.run(SnapshotMode.local_full)

        plan: DiffPlan = self.diff_planner.run(DiffInput(remote_full, local_full))

        if plan.diff_files:
            self.error_handler.run(
                ErrorEvent(ErrorNumber.diff_files, plan.diff_files)
            )

        report = self.repository_validator.run(local_full)

        conflicts = self.repository_validator.run(local_full)

        if conflicts:
            self.error_handler.run(
                ErrorEvent(code=ErrorNumber.conflict_files, details=conflicts)
            )
