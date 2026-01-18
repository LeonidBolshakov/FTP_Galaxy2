from pathlib import Path
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
    SaveInput,
)
from SRC.SYNC_APP.PORTS.ports import (
    ExecutionGate,
    SnapshotService,
    DiffPlanner,
    TransferService,
    RepositoryValidator,
    ValidateService,
    SaveService,
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
            validate_service: ValidateService,
            save_service: SaveService,
        execution_gate: ExecutionGate,
            report_service: ReportService,
    ):
        self.ftp = ftp
        self.runtime_context = runtime_context
        self.snapshot_service = snapshot_service
        self.diff_planner = diff_planner
        self.transfer_service = transfer_service
        self.repository_validator = repository_validator
        self.validate_service = validate_service
        self.save_service = save_service
        self.execution_gate = execution_gate
        self.report_service = report_service

    def run(self) -> None:
        if self.execution_gate.check(self.runtime_context) == ExecutionChoice.SKIP:
            return

        general_report: ReportItems = []
        new_dir = self.runtime_context.app.new_dir_path

        local_snap_before, remote_snap_before = self._get_lite_snapshots()
        plan = self._plan_diff(
            local_snap=local_snap_before, remote_snap=remote_snap_before
        )

        general_report.extend(plan.report_plan)

        self._download(plan=plan)

        local_snap_after, remote_snap_after = self._get_full_snapshots_only_for(
            plan=plan, new_dir=new_dir
        )
        is_validate_commit, report_validate = self._validate_and_commit(
            plan=plan,
            new_dir=new_dir,
            local_snap=local_snap_after,
            remote_snap=remote_snap_after,
            delete=plan.to_delete,
        )
        general_report.extend(report_validate)

        conflicts_report: ReportItems = self._validate_repository(
            local=local_snap_after
        )
        general_report.extend(conflicts_report)
        self._report(is_validate_commit=is_validate_commit, report=general_report)

    def _get_lite_snapshots(self) -> tuple[RepositorySnapshot, RepositorySnapshot]:
        local_before = self.snapshot_service.local(
            SnapshotInput(
                context=self.runtime_context,
                mode=ModeSnapshot.LITE_MODE,
                local_dir=self.runtime_context.app.local_dir,
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
            self, local_snap: RepositorySnapshot, remote_snap: RepositorySnapshot
    ) -> DiffPlan:

        stop_list_mode = (
            ModeDiffPlan.USE_STOP_LIST
            if self.runtime_context.use_stop_list
            else ModeDiffPlan.NOT_USE_STOP_LIST
        )

        plan: DiffPlan = self.diff_planner.run(
            DiffInput(
                context=self.runtime_context,
                local_snap=local_snap,
                remote_snap=remote_snap,
                stop_list_mode=stop_list_mode,
            )
        )

        return plan

    def _download(self, plan: DiffPlan) -> None:
        self.transfer_service.run(
            TransferInput(
                context=self.runtime_context,
                ftp=self.ftp,
                schnapsots_for_loading=plan.to_download,
            )
        )

    def _get_full_snapshots_only_for(
            self, plan: DiffPlan, new_dir: Path
    ) -> tuple[RepositorySnapshot, RepositorySnapshot]:
        only_for = {s.name.strip() for s in plan.to_download}

        local_snap_after = self.snapshot_service.local(
            SnapshotInput(
                context=self.runtime_context,
                local_dir=new_dir,
                mode=ModeSnapshot.FULL_MODE,
                only_for=only_for,
            )
        )

        remote_snap_after = self.snapshot_service.remote(
            SnapshotInput(
                context=self.runtime_context,
                ftp=self.ftp,
                mode=ModeSnapshot.FULL_MODE,
                only_for=only_for,
            )
        )

        return local_snap_after, remote_snap_after

    def _validate_and_commit(
            self,
            plan: DiffPlan,
            new_dir: Path,
            local_snap: RepositorySnapshot,
            remote_snap: RepositorySnapshot,
            delete: list[FileSnapshot],
    ) -> tuple[bool, ReportItems]:
        report_validate = self.validate_service.run(
            ValidateInput(
                context=self.runtime_context,
                plan=plan,
                new_dir=new_dir,
                local_snap=local_snap,
                remote_snap=remote_snap,
            )
        )
        print("*->", report_validate, "<-*")
        is_validate_commit = True if report_validate else False

        return (
            is_validate_commit,
            report_validate,
        )

        if is_validate_commit:
            self.save_service.commit_keep_new_old_files(
                data=SaveInput(context=self.runtime_context, delete=delete)
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
