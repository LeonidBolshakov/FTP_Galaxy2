"""Контроллер синхронизации локального и удалённого репозиториев (оркестратор приложения).

Модуль содержит `SyncController` — тонкий слой оркестрации, который связывает порты/сервисы
приложения (снимки, планирование различий, трансфер, валидация, коммит и отчёт).

Контроллер намеренно почти не содержит бизнес-логики:
— принимает зависимости через конструктор,
— вызывает порты/сервисы в фиксированном порядке,
— агрегирует отчёты и выставляет общий флаг успешности.

Ошибки "нижнего уровня" (FTP/файлы/валидация и т.п.) обычно поднимаются как доменные
исключения внутри сервисов и обрабатываются на уровне точки входа (main.py).
"""

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
    ValidateInput,
    ReportItemInput,
    ReportItems,
    Ftp,
    RepositorySnapshot,
    SaveInput,
    ValidCommitInput,
)
from SRC.SYNC_APP.APP.ports import (
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
    """Оркестратор этапов синхронизации.

    Параметры (зависимости) передаются извне — контроллер не создаёт сервисы сам.
    Это упрощает тестирование и позволяет менять реализации портов без изменения контроллера.

    Атрибуты:
        ftp: адаптер FTP (порт/адаптер к инфраструктуре).
        runtime_context: контекст выполнения (конфиг + параметры запуска).
        snapshot_service: сервис получения снимков локального/удалённого репозитория.
        diff_planner: сервис построения плана загрузки/перемещения файлов.
        transfer_service: сервис загрузки/перемещения файлов согласно плану.
        repository_validator: дополнительные проверки репозитория после выполнения.
        validate_service: проверка скачанного/полученного результата перед коммитом.
        save_service: коммит/сохранение результата
        execution_gate: "шлюз" выполнения — принимает решение SKIP/RUN и фиксирует факт/дату запуска.
        report_service: формирование/сохранение отчёта.
    """

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
        """Сохраняет зависимости (порты/сервисы) для последующего запуска `run()`.

        Parameters
        ----------
        ftp
            FTP-адаптер (доступ к удалённому хранилищу)
        runtime_context
            Контекст выполнения (конфигурация + параметры запуска)
        snapshot_service
            Сервис построения снимков локального/удалённого состояния
        diff_planner
            Сервис построения плана переноса/скачивания файлов
        transfer_service
            Сервис переноса/скачивания файлов по плану
        repository_validator
            Сервис дополнительных проверок репозитория
        validate_service
            Сервис валидации результата перед коммитом
        save_service
            Сервис коммита/сохранения результата
        execution_gate
            Шлюз выполнения: решает, можно ли запускаться, и записывает факт выполнения
        report_service
            Сервис формирования отчёта.
        """
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
        """Выполняет полный цикл синхронизации.

        Общая последовательность:
        1) ExecutionGate: принять решение о запуске (например, "не чаще раза в день").
        2) Построить "лёгкие" снимки до загрузки (LITE_MODE).
        3) Построить план различий (DiffPlanner).
        4) Скачать файлы по плану (TransferService).
        5) Построить "полные" снимки только для скачанных файлов (FULL_MODE + only_for).
        6) Провести валидацию и, при успехе, выполнить коммит/фиксацию результата.
        7) Запустить дополнительные проверки репозитория и сформировать общий отчёт.

        Notes
        -----
        Контроллер не подавляет исключения сервисов: ожидается, что верхний уровень
        (точка входа/CLI) отловит и переведёт их в код завершения и/или сообщение пользователю.
        """
        # При необходимости пропускаем запуск (например, ограничение "once per day").
        if self.execution_gate.check(self.runtime_context) == ExecutionChoice.SKIP:
            return

        general_report: ReportItems = []
        new_dir = self.runtime_context.app.new_dir_path

        # Снимки "до" (облегчённый режим: быстро и достаточно для построения плана).
        local_snap_before, remote_snap_before = self._get_lite_snapshots()

        plan_before, is_validate_plan, report = self.diff_planner.run(
            DiffInput(
                context=self.runtime_context,
                local_snap=local_snap_before,
                remote_snap=remote_snap_before,
            )
        )
        general_report += report

        # Скачивание файлов по плану; ошибки на отдельных файлах отражаются в report.
        is_validate_download, report = self.transfer_service.run(
            TransferInput(
                context=self.runtime_context,
                ftp=self.ftp,
                snapshots_for_loading=plan_before.to_download,
            )
        )
        general_report += report

        # Полные снимки — только для тех файлов, которые скачивали по плану.
        local_snap_after, remote_snap_after = self._get_full_snapshots_only_for(
            plan=plan_before, new_dir=new_dir
        )

        # Валидация результата и условный "коммит" (перемещения/сохранение директорий).
        valid_commit_input = ValidCommitInput(
            plan=plan_before,
            new_dir=new_dir,
            local_snap=local_snap_after,
            remote_snap=remote_snap_after,
            delete=plan_before.to_delete,
            is_validate=all([is_validate_plan, is_validate_download]),
        )
        is_validate_commit, report_validate = self._validate_commit_execution_gate(
            valid_commit_inpit=valid_commit_input
        )

        general_report += report_validate

        # Дополнительные проверки репозитория (поверх проверки/коммита).
        local_dir: Path = self.runtime_context.app.local_dir
        local_files_names = [p.name for p in Path(local_dir).iterdir() if p.is_file()]
        report_repositoty_error = self.repository_validator.run(
            ValidateRepositoryInput(
                context=self.runtime_context, names=local_files_names
            )
        )

        general_report += report_repositoty_error

        # Итоговый флаг успешности всех этапов (используется для отчёта).
        is_validate = all([is_validate_plan, is_validate_commit, is_validate_download])
        self.put_report(is_validate=is_validate, general_report=general_report)

    # -----
    #
    # -----

    def _get_lite_snapshots(self) -> tuple[RepositorySnapshot, RepositorySnapshot]:
        """Строит облегчённые снимки локального и удалённого репозитория.

        Returns
        -------
            (local_before, remote_before) — снимки в режиме `ModeSnapshot.LITE_MODE`.
        """
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

    def _get_full_snapshots_only_for(
            self, plan: DiffPlan, new_dir: Path
    ) -> tuple[RepositorySnapshot, RepositorySnapshot]:
        """Строит "полные" снимки только для файлов, которые должны были скачаться.

        Parameters
        ----------
        plan
            План различий; используется список `plan.to_download`.
        new_dir
            Путь к директории, куда скачивались новые файлы (локальный снимок берётся из неё).

        Returns
        -------
        tuple[RepositorySnapshot, RepositorySnapshot]
            (local_after, remote_after) — снимки в режиме `ModeSnapshot.FULL_MODE`
            с ограничением `only_for` (только выбранные файлы).
        """
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

    def _validate_commit_execution_gate(
            self, valid_commit_inpit: ValidCommitInput
    ) -> tuple[bool, ReportItems]:
        """Валидирует результат и, при успехе, выполняет коммит и фиксирует запуск.

        Parameters
        ----------
        valid_commit_inpit.plan
            План различий (используется валидатором).
        valid_commit_inpit.new_dir
            Директория с новой версией файлов.
        valid_commit_inpit.local_snap
            Локальный снимок после скачивания (обычно FULL_MODE, только скачанные файлы).
        valid_commit_inpit.remote_snap
            Удалённый снимок для тех же файлов (для сравнения/проверок).
        valid_commit_inpit.delete
            Список файлов, которые должны быть удалены (используется в commit).
        valid_commit_inpit.is_validate
            Предикат "можно ли коммитить": зависит от предыдущих стадий (план + скачивание).

        Returns
        -------
            is_validate_commit
                Результат валидации (True → можно коммитить, если is_validate тоже True).
            report
                Отчёт валидации + (опционально) отчёт коммита.
        """
        is_validate_commit, report_validate = self.validate_service.run(
            ValidateInput(
                context=self.runtime_context,
                plan=valid_commit_inpit.plan,
                new_dir=valid_commit_inpit.new_dir,
                local_snap=valid_commit_inpit.local_snap,
                remote_snap=valid_commit_inpit.remote_snap,
            )
        )

        report_commit: ReportItems = []

        # Коммитим только если все предыдущие этапы прошли без ошибок и текущая проверка успешна.
        if valid_commit_inpit.is_validate and is_validate_commit:
            report_commit = self.save_service.commit_keep_new_old_dirs(
                data=SaveInput(
                    context=self.runtime_context, delete=valid_commit_inpit.delete
                )
            )
        # Фиксируем факт выполнения.
        self.execution_gate.record_run(ctx=self.runtime_context)

        return is_validate_commit, report_validate + report_commit

    def put_report(self, is_validate: bool, general_report: ReportItems):
        """Формирует итоговый отчёт выполнения.

        Parameters
        ----------
        is_validate
            Итоговый флаг успешности (агрегированный по этапам run())
        general_report
            Список сообщений/ошибок, накопленный за все этапы.
        """
        self.report_service.run(
            ReportItemInput(
                context=self.runtime_context,
                is_validate_commit=is_validate,
                report=general_report,
            ),
        )
