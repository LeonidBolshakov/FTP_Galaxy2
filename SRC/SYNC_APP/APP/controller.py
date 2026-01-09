from ftplib import FTP
from typing import Callable

from SRC.SYNC_APP.APP.dto import (
    RuntimeContext,
    ExecutionChoice,
    DiffPlan,
    ErrorNumber,
    TransferMode,
    ErrorEvent,
    TransferInput,
    DiffInput,
    SnapshotInput,
    ValidateRepositoryInput,
    ModeSnapShop,
    ModeDiffPlan,
)
from SRC.SYNC_APP.PORTS.ports import (
    ExecutionGate,
    SnapshotService,
    DiffPlanner,
    TransferService,
    RepositoryValidator,
    ErrorHandler,
)


class SyncController:
    def __init__(
        self,
            ftp_parameter: FTP,
            setup_loguru: Callable,
        runtime_context: RuntimeContext,
        snapshot_service: SnapshotService,
        diff_planner: DiffPlanner,
        transfer_service: TransferService,
        repository_validator: RepositoryValidator,
        error_handler: ErrorHandler,
        execution_gate: ExecutionGate,
    ):
        self.ftp_parameter = ftp_parameter
        self.setup_loguru = setup_loguru
        self.runtime_context = runtime_context
        self.snapshot_service = snapshot_service
        self.diff_planner = diff_planner
        self.transfer_service = transfer_service
        self.repository_validator = repository_validator
        self.error_handler = error_handler
        self.execution_gate = execution_gate

    # fmt: on
    def run(self) -> None:
        self.setup_loguru(self.runtime_context)

        if self.execution_gate.check(self.runtime_context) == ExecutionChoice.SKIP:
            return

        ftp = self.ftp_parameter
        remote_before = self.snapshot_service.remote(
            SnapshotInput(self.runtime_context, ftp, ModeSnapShop.LITE_MODE)
        )
        local_before = self.snapshot_service.local(
            SnapshotInput(self.runtime_context, ftp, ModeSnapShop.LITE_MODE)
        )

        pre_plan: DiffPlan = self.diff_planner.run(
            DiffInput(
                self.runtime_context,
                local_before,
                remote_before,
                (
                    ModeDiffPlan.USE_STOP_LIST
                    if self.runtime_context.use_stop_list
                    else ModeDiffPlan.USE_STOP_LIST
                ),
            )
        )

        if pre_plan.diff_files:
            self.error_handler.run(
                ErrorEvent(
                    self.runtime_context,
                    ErrorNumber.diff_pre_files,
                    pre_plan.diff_files,
                )
            )

        self.transfer_service.run(
            TransferInput(
                self.runtime_context, ftp, TransferMode.delete, pre_plan.to_delete
            )
        )

        self.transfer_service.run(
            TransferInput(
                self.runtime_context, ftp, TransferMode.download, pre_plan.to_download
            )
        )

        remote_after = self.snapshot_service.remote(
            SnapshotInput(
                self.runtime_context, ftp, ModeSnapShop.FULL_MODE, only_for=set()
            )
        )
        local_after = self.snapshot_service.local(
            SnapshotInput(
                self.runtime_context, ftp, ModeSnapShop.FULL_MODE, only_for=set()
            )
        )

        post_plan: DiffPlan = self.diff_planner.run(
            DiffInput(
                context=self.runtime_context,
                local=local_after,
                remote=remote_after,
                use_stop_list=ModeDiffPlan.NOT_USE_STOP_LIST,
            )
        )

        if post_plan.diff_files:
            self.error_handler.run(
                ErrorEvent(
                    self.runtime_context,
                    ErrorNumber.diff_download_files,
                    post_plan.diff_files,
                )
            )

        conflicts = self.repository_validator.run(
            ValidateRepositoryInput(self.runtime_context, local_after)
        )

        if conflicts:
            self.error_handler.run(
                ErrorEvent(
                    self.runtime_context,
                    code=ErrorNumber.conflict_files,
                    details=conflicts,
                )
            )

        self.execution_gate.record_run(self.runtime_context)
