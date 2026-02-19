from pathlib import Path
from typing import Self

from pydantic_settings import SettingsConfigDict
from pydantic import (
    model_validator,
    BaseModel,
)


class CommonConfig(BaseModel):
    """
    Конфигурация приложения.

    Загружается при старте и используется как источник настроек.

    Примечание:
        new_dir и old_dir могут не задаваться в YAML — в этом случае они вычисляются
        на основе local_dir (см валидатор _derive_dirs()).
    """

    model_config = SettingsConfigDict(
        # Запрещаем неизвестные ключи в YAML, чтобы не “проглатывать” опечатки.
        extra="forbid",
    )
    # fmt: off
    local_dir                       : Path

    # Локальный репозиторий
    new_dir                         : Path | None                   = None
    old_dir                         : Path | None                   = None
    # fmt: on

    @model_validator(mode="after")
    def _derive_dirs(self) -> Self:
        """
        Довычисляет производные директории, если они не заданы.

        Логика:
            - если new_dir не задан, используем local_dir / "NEW"
            - если old_dir не задан, используем local_dir / "OLD"

        Возвращает:
            Тот же экземпляр модели (Self) после возможных дополнений.

        Важно:
            Этот валидатор запускается после основной валидации модели.
        """
        # если new_dir/old_dir не заданы в YAML — считаем от local_dir
        if self.new_dir is None:
            self.new_dir = self.local_dir / "NEW"
        if self.old_dir is None:
            self.old_dir = self.local_dir / "OLD"
        return self
