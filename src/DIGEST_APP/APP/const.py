from enum import StrEnum
from typing import Final

EMPTY = "?????"


class DigestColumnConfigKey(StrEnum):
    TASK = "task"
    COMPONENTS = "components"
    DESCRIPTION = "description"
    WHAT_CHANGED = "what_changed"
    HOW_CHANGED = "how_changed"


class HorizontalAlignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VerticalAlignment(StrEnum):
    TOP = "top"
    CENTER = "center"
    RIGHT = "botto"


class DigestSectionTitle(StrEnum):
    TASK = "ЗАДАЧА В JIRA"
    COMPONENTS = "КОМПОНЕНТЫ"
    FIRST_SOLUTION = "ПЕРВОЕ РЕШЕНИЕ"  # служебная секция: только фильтр
    DESCRIPTION = "КРАТКОЕ ОПИСАНИЕ"
    WHAT_HAS_CHANGED = "ЧТО ИЗМЕНЕНО"
    HOW_IT_CHANGED = "КАК ИЗМЕНЕНО"

    @classmethod
    def all_titles(cls) -> list[str]:
        return [k.value for k in cls]


class DigestSectionKeys:
    TASK: Final[str] = DigestSectionTitle.TASK.value
    COMPONENTS: Final[str] = DigestSectionTitle.COMPONENTS.value
    FIRST_SOLUTION: Final[str] = DigestSectionTitle.FIRST_SOLUTION.value
    DESCRIPTION: Final[str] = DigestSectionTitle.DESCRIPTION.value
    WHAT_HAS_CHANGED: Final[str] = DigestSectionTitle.WHAT_HAS_CHANGED.value
    HOW_IT_CHANGED: Final[str] = DigestSectionTitle.HOW_IT_CHANGED.value

    @classmethod
    def all(cls) -> list[str]:
        return DigestSectionTitle.all_titles()
