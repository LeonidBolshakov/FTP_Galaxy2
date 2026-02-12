from dataclasses import dataclass

from DIGEST_APP.CONFIG.config import DigestConfig


@dataclass(frozen=True)
class RuntimeContext:
    """Контекст выполнения приложения.

    Содержит конфигурацию и параметры запуска, которые передаются в сервисы/адаптеры.

    Attributes
    ----------
    """

    app: DigestConfig


@dataclass
class DescriptionOfNewTask:
    task: str
    first_solution: str
    components: list[str]
    description: str
    what_has_changed: str
    how_it_changed: str
