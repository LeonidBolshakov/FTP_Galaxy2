from SYNC_APP.APP.types import (
    ModeDiffPlan,
    ModeSnapshot,
    ValidateCommitResult,
    ErrorNumber,
    ExecutionChoice,
    StatusReport,
)


def test_enums_have_unique_values():
    """Убедитесь, что каждое перечисление содержит уникальные имена и значения членов."""
    for enum_cls in [
        ModeDiffPlan,
        ModeSnapshot,
        ValidateCommitResult,
        ErrorNumber,
        ExecutionChoice,
        StatusReport,
    ]:
        names = [m.name for m in enum_cls]
        values = [m.value for m in enum_cls]
        # имена уникальны
        assert len(names) == len(set(names))
        # значения должны быть уникальны
        assert len(values) == len(set(values))
