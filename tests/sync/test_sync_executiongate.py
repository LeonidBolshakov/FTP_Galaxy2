from SYNC_APP.INFRA.executiongate import ExecutionGate
from SYNC_APP.APP.dto import RuntimeContext
from SYNC_APP.APP.types import ExecutionChoice, ModeDiffPlan


def _ctx(tmp_path, once_per_day: bool):
    """
    Создаёт минимальный RuntimeContext для тестов ExecutionGate.

    Вместо использования SyncConfig (у которого поля неизменяемы) применяем SimpleNamespace
    с необходимыми атрибутами (local_dir, new_dir, date_file). Это позволяет избежать
    изменения доступных только для чтения свойств экземпляров SyncConfig и достаточно
    для логики ExecutionGate, которая обращается только к этим атрибутам.
    """
    from types import SimpleNamespace

    # Create a simple app-like object with the required attributes.
    app_stub = SimpleNamespace(
        local_dir=tmp_path,
        new_dir=tmp_path / "NEW",
        date_file=tmp_path / "date_file",
    )
    return RuntimeContext(
        app=app_stub,
        once_per_day=once_per_day,
        mode_stop_list=ModeDiffPlan.NOT_USE_STOP_LIST,
    )


def test_check_without_once_per_day(tmp_path):
    ctx = _ctx(tmp_path, once_per_day=False)
    gate = ExecutionGate()
    assert gate.check(ctx) is ExecutionChoice.RUN


def test_check_with_once_per_day_no_file(tmp_path):
    ctx = _ctx(tmp_path, once_per_day=True)
    gate = ExecutionGate()
    # файл date_file не существует
    assert gate.check(ctx) is ExecutionChoice.RUN


def test_check_with_once_per_day_same_date(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, once_per_day=True)
    # записываем сегодняшнюю дату в файл
    date_str = "2024-02-27"
    ctx.app.date_file.write_text(date_str)
    gate = ExecutionGate()
    # Переопределяем _today_stamp так, чтобы она возвращала ту же дату
    monkeypatch.setattr(gate, "_today_stamp", lambda: date_str)
    assert gate.check(ctx) is ExecutionChoice.SKIP


def test_record_run_writes_date(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, once_per_day=True)
    gate = ExecutionGate()
    date_str = "2024-02-28"
    monkeypatch.setattr(gate, "_today_stamp", lambda: date_str)
    gate.record_run(ctx)
    # теперь файл должен содержать дату
    assert ctx.app.date_file.read_text().strip() == date_str
