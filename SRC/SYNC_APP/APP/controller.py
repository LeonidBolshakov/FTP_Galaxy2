from SRC.SYNC_APP.APP.dto import (
    RuntimeContext,
    ExecutionChoice,
    DiffPlan,
    TransferInput,
    DiffInput,
    SnapshotInput,
    ValidateRepositoryInput,
    ModeSnapshot,
    ModeDiffPlan,
    ValidateInput,
    ReportItemInput,
    ReportItems,
    Ftp,
    RepositorySnapshot,
    FileSnapshot,
)
from SRC.SYNC_APP.PORTS.ports import (
    ExecutionGate,
    SnapshotService,
    DiffPlanner,
    TransferService,
    RepositoryValidator,
    ValidateAndSaveService,
    ReportService,
)


class SyncController:
    def __init__(
        self,
            ftp: Ftp,
        runtime_context: RuntimeContext,
        snapshot_service: SnapshotService,
        diff_planner: DiffPlanner,
        transfer_service: TransferService,
        repository_validator: RepositoryValidator,
            validate_and_save_service: ValidateAndSaveService,
        execution_gate: ExecutionGate,
            report_service: ReportService,
    ):
        self.ftp = ftp
        self.runtime_context = runtime_context
        self.snapshot_service = snapshot_service
        self.diff_planner = diff_planner
        self.transfer_service = transfer_service
        self.repository_validator = repository_validator
        self.validate_and_save_service = validate_and_save_service
        self.execution_gate = execution_gate
        self.report_service = report_service

    def run(self) -> None:
        if self.execution_gate.check(self.runtime_context) == ExecutionChoice.SKIP:
            return

        general_report: ReportItems = []

        local_before, remote_before = self._get_lite_snapshots()
        pre_plan = self._plan_diff(local=local_before, remote=remote_before)

        general_report.extend(pre_plan.report_plan)

        self._download_if_needed(plan=pre_plan)
        local_after, remote_after = self._get_full_snapshots_only_for(plan=pre_plan)
        is_validate_commit, report_validate = self._validate_and_commit(
            local=local_after, remote=remote_after, delete=pre_plan.to_delete
        )
        general_report.extend(report_validate)
        conflicts_report: ReportItems = self._validate_repository(local=local_after)
        general_report.extend(conflicts_report)
        self._report(is_validate_commit=is_validate_commit, report=general_report)

    def _get_lite_snapshots(self) -> tuple[RepositorySnapshot, RepositorySnapshot]:
        local_before = self.snapshot_service.local(
            SnapshotInput(
                context=self.runtime_context,
                mode=ModeSnapshot.LITE_MODE,
            )
        )
        remote_before = self.snapshot_service.remote(
            SnapshotInput(
                context=self.runtime_context,
                mode=ModeSnapshot.LITE_MODE,
                ftp=self.ftp,
            )
        )

        return local_before, remote_before

    def _plan_diff(
            self, local: RepositorySnapshot, remote: RepositorySnapshot
    ) -> DiffPlan:

        stop_list_mode = (
            ModeDiffPlan.USE_STOP_LIST
            if self.runtime_context.use_stop_list
            else ModeDiffPlan.NOT_USE_STOP_LIST
        )

        plan: DiffPlan = self.diff_planner.run(
            DiffInput(
                context=self.runtime_context,
                local=local,
                remote=remote,
                stop_list_mode=stop_list_mode,
            )
        )

        return plan

    def _download_if_needed(self, plan: DiffPlan) -> None:
        if plan.to_download:
            self.transfer_service.run(
                TransferInput(
                    context=self.runtime_context,
                    ftp=self.ftp,
                    snapshots=plan.to_download,
                )
            )

    def _get_full_snapshots_only_for(
            self, plan: DiffPlan
    ) -> tuple[RepositorySnapshot, RepositorySnapshot]:
        only_for = {s.name.strip() for s in plan.to_download}

        local_after = self.snapshot_service.local(
            SnapshotInput(
                context=self.runtime_context,
                mode=ModeSnapshot.FULL_MODE,
                only_for=only_for,
            )
        )

        remote_after = self.snapshot_service.remote(
            SnapshotInput(
                context=self.runtime_context,
                ftp=self.ftp,
                mode=ModeSnapshot.FULL_MODE,
                only_for=only_for,
            )
        )

        return local_after, remote_after

    def _validate_and_commit(
            self,
            local: RepositorySnapshot,
            remote: RepositorySnapshot,
            delete: list[FileSnapshot],
    ) -> tuple[bool, ReportItems]:
        is_validate_commit, report_validate = self.validate_and_save_service.validate(
            ValidateInput(
                context=self.runtime_context, local=local, remote=remote, delete=delete
            )
        )

        if is_validate_commit:
            self.validate_and_save_service.commit_keep_new_old_files(
                data=self.runtime_context
            )
            self.execution_gate.record_run(ctx=self.runtime_context)

        return is_validate_commit, report_validate

    def _validate_repository(self, local) -> ReportItems:
        return self.repository_validator.run(
            ValidateRepositoryInput(self.runtime_context, local)
        )

    def _report(self, is_validate_commit: bool, report: ReportItems):
        self.report_service.run(
            ReportItemInput(
                context=self.runtime_context,
                is_validate_commit=is_validate_commit,
                report=report,
            ),
        )
