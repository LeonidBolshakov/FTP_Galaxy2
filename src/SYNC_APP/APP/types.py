from enum import Enum, auto


class ModeDiffPlan(Enum):
    USE_STOP_LIST = auto()
    NOT_USE_STOP_LIST = auto()


class ModeSnapshot(Enum):
    """Режим построения снимка (snapshot)."""
    LITE_MODE = auto()
    FULL_MODE = auto()


class ValidateCommitResult(Enum):
    """Результат валидации/коммита (если используется отдельная модель результата)."""
    SUCCESS = auto()
    FAILURE = auto()
    UNKNOWN = auto()


class ErrorNumber(Enum):
    """Идентификаторы ошибок/разделов отчёта (группировка сообщений)."""
    diff_pre_files = auto()
    diff_download_files = auto()
    conflict_files = auto()


class ExecutionChoice(Enum):
    """Решение `ExecutionGate`: выполнять цикл или пропустить."""
    RUN = auto()
    SKIP = auto()


class StatusReport(Enum):
    """Уровень важности/серьёзности сообщения в отчёте."""
    INFO = auto()
    IMPORTANT_INFO = auto()
    WARNING = auto()
    ERROR = auto()
    FATAL = auto()
