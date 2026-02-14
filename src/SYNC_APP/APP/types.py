from enum import Enum, auto


class ModeDiffPlan(Enum):
    USE_STOP_LIST = auto()
    NOT_USE_STOP_LIST = auto()


class ModeSnapshot(Enum):
    LITE_MODE = auto()
    FULL_MODE = auto()
