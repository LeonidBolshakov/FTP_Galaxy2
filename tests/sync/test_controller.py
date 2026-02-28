"""Комплексный тест для оркестратора SyncController.

В этом тесте предоставляются фиктивные реализации всех зависимостей и проверяется,
что контроллер вызывает свои компоненты в правильном порядке и возвращает
ожидаемый код статуса, когда все этапы проходят успешно.
"""

from types import SimpleNamespace

from SYNC_APP.APP.dto import (
    RuntimeContext,
    RepositorySnapshot,
    FileSnapshot,
    DiffPlan,
)
from SYNC_APP.APP.types import ExecutionChoice, ModeDiffPlan
from SYNC_APP.APP.controller import SyncController


def test_controller_runs_full_cycle(tmp_path):
    # Список имён вызовов и их аргументов для проверки порядка и количества вызовов.
    calls = []

    # Определяем статический снимок репозитория, который используется сервисом снимков.
    repo_files = {
        "abc.txt": FileSnapshot("abc.txt", 12345, "N13Q"),
        "cba.txt": FileSnapshot("cba.txt", 11111, None),
    }
    repository_snapshot = RepositorySnapshot(repo_files.copy())

    # Заглушка FTP‑адаптера (не используется напрямую в этом тесте).
    class DummyFtp:
        pass

    # Заглушка сервиса снимков, которая записывает вызовы и всегда возвращает один и тот же снимок.
    class SnapshotSvc:
        def local(self, data):
            calls.append(("SnapshotSvc.local", data))
            return repository_snapshot

        def remote(self, data):
            calls.append(("SnapshotSvc.remote", data))
            return repository_snapshot

    # Заглушка планировщика различий, который использует снимок для построения плана,
    # в котором все файлы запланированы для загрузки.
    class DiffPlannerSvc:
        def run(self, data):
            calls.append(("DiffPlanner.run", data))
            # Планируется загрузка обоих файлов; удалений нет.
            plan = DiffPlan(
                to_delete=[],
                to_download=[repo_files["abc.txt"], repo_files["cba.txt"]],
            )
            return plan, True, []

    # Заглушка сервиса передачи, который всегда завершается успешно и возвращает пустой отчёт.
    class TransferSvc:
        def run(self, data):
            calls.append(("TransferService.run", data))
            return True, []

    # Заглушка сервиса валидации, который всегда завершается успешно и возвращает пустой отчёт.
    class ValidateSvc:
        def run(self, data):
            calls.append(("ValidateService.run", data))
            return True, []

    # Заглушка сервиса сохранения, который записывает вызовы и возвращает пустой список отчётов.
    class SaveSvc:
        def commit_keep_new_old_dirs(self, data):
            calls.append(("SaveService.commit", data))
            return []

    # Заглушка валидатора репозитория, который записывает вызовы и не возвращает дополнительных ошибок.
    class RepoValidatorSvc:
        def run(self, data):
            calls.append(("RepositoryValidator.run", data))
            return []

    # Заглушка сервиса отчётов, который записывает вызовы.
    class ReportSvc:
        def run(self, data):
            calls.append(("ReportService.run", data))

    # Заглушка контрольного шлюза, который всегда разрешает выполнение и записывает свои вызовы.
    class ExecutionGateSvc:
        def check(self, ctx):
            calls.append(("ExecutionGate.check", ctx))
            return ExecutionChoice.RUN

        def record_run(self, ctx):
            calls.append(("ExecutionGate.record_run", ctx))

    # Подготавливаем контекст выполнения с фиктивными локальной и новой директориями.
    local_dir = tmp_path / "LOCAL"
    new_dir = tmp_path / "NEW"
    local_dir.mkdir()
    new_dir.mkdir()
    runtime_context = RuntimeContext(
        app=SimpleNamespace(local_dir=local_dir, new_dir=new_dir),
        once_per_day=False,
        mode_stop_list=ModeDiffPlan.NOT_USE_STOP_LIST,
    )

    # Instantiate controller with all stub services.
    controller = SyncController(
        ftp=DummyFtp(),
        runtime_context=runtime_context,
        snapshot_service=SnapshotSvc(),
        diff_planner=DiffPlannerSvc(),
        transfer_service=TransferSvc(),
        execution_gate=ExecutionGateSvc(),
        repository_validator=RepoValidatorSvc(),
        validate_service=ValidateSvc(),
        save_service=SaveSvc(),
        report_service=ReportSvc(),
    )

    # Запускаем контроллер и проверяем успешный статус.
    result = controller.run()
    assert (
            result == 0
    ), "Ожидалось, что контроллер вернёт код успеха (0), когда все этапы прошли успешно."

    # Verify the sequence of method calls matches the expected orchestrator flow.
    expected_call_order = [
        "ExecutionGate.check",  # проверка перед выполнением работы
        "SnapshotSvc.local",  # лёгкий локальный снимок
        "SnapshotSvc.remote",  # лёгкий удалённый снимок
        "DiffPlanner.run",  # построение плана
        "TransferService.run",  # загрузка файлов согласно плану
        "SnapshotSvc.local",  # полный локальный снимок (только для plan.to_download)
        "SnapshotSvc.remote",  # полный удалённый снимок (только для plan.to_download)
        "ValidateService.run",  # валидация результата
        "SaveService.commit",  # сохранение (коммит), так как валидация прошла успешно
        "ExecutionGate.record_run",  # запись запуска в шлюзе
        "RepositoryValidator.run",  # посткоммитная валидация репозитория
        "ReportService.run",  # финальный отчёт
    ]

    # Extract only the call names from the recorded calls list.
    actual_call_order = [name for name, _ in calls]
    assert (
            actual_call_order == expected_call_order
    ), f"Unexpected call sequence: {actual_call_order}"
