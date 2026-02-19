"""
Конфигурация приложения и загрузка настроек из YAML.

Содержит:
- Pydantic-модели для настроек логирования (консоль/файл).
- Основную модель настроек приложения (SyncConfig) на базе BaseSettings.
- Функцию load_config() для чтения YAML и валидации конфигурации.
"""

from pathlib import PurePosixPath
from typing import Literal
from pathlib import Path
from typing import Self

from pydantic import (
    PositiveInt,
    PositiveFloat,
    computed_field,
)
from loguru import logger
from pydantic import (
    model_validator,
    Field,
    BaseModel,
)

from GENERAL.config import CommonConfig
from SYNC_APP.INFRA.utils import default_log_dir, date_file_path


# ----------------------------
# Logging config (loguru)
# ----------------------------


class ConsoleLoggingConfig(BaseModel):
    """
    Настройки логирования в консоль (loguru).

    Attributes:
        level: Уровень логирования (например, "INFO", "DEBUG").
        format: Формат сообщения для loguru (разметка/плейсхолдеры loguru).
    """

    level: str = "INFO"
    format: str = "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"


class FileLoggingConfig(BaseModel):
    """
    Настройки логирования в файл (loguru).

    Attributes:
        level: Уровень логирования для файла.
        path: Путь к файлу лога (относительный или абсолютный).
        rotation: Правило ротации (например, "1 MB", "1 day" и т.п по правилам loguru).
        format: Формат записи в файл.
        retention: Политика хранения старых логов (опционально).
        compression: Сжатие архивов логов (опционально).
    """

    level: str = "DEBUG"
    path: Path | None = None
    name: str | None = None
    rotation: str = "1 MB"
    format: str = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | "
        "{file.name}:{function}:{line} - {message}"
    )
    retention: str = "7 days"
    compression: str = "zip"

    @model_validator(mode="after")
    def _finalize(self) -> Self:
        if self.path is None and self.name is None:
            logger.warning(
                "Параметры. Для файла логирования не заданы ни полный путь, ни имя\n"
                "Будут использоваться значения по умолчанию"
            )

        name = self.name or "FTP.log"
        p = self.path

        if p is None:
            self.path = default_log_dir() / name
            return self

        if p.suffix:  # пользователь указал файл
            return self

        # иначе считаем директорией
        self.path = p / name
        return self


class LoggingConfig(BaseModel):
    """
    Группа настроек логирования.

    Attributes:
        console: Настройки консольного логирования.
        file: Настройки файлового логирования.
    """

    console: ConsoleLoggingConfig = Field(default_factory=ConsoleLoggingConfig)
    file: FileLoggingConfig = Field(default_factory=FileLoggingConfig)


# ----------------------------
# Основная конфигурация приложения
# ----------------------------


class SyncConfig(CommonConfig):
    """Конфигурация приложения"""

    # fmt: off
    # Logging
    logging: LoggingConfig          = Field(default_factory=LoggingConfig)
    # FTP
    ftp_root                        : PurePosixPath
    ftp_username                    : Literal["anonymous"]          = "anonymous"
    ftp_host                        : Literal["ftp.galaktika.ru"]   = "ftp.galaktika.ru"
    ftp_timeout_sec                 : PositiveFloat                 = 3
    ftp_repeat                      : PositiveInt                   = 3
    ftp_retry_delay_seconds         : PositiveFloat                 = 1
    ftp_blocksize                   : PositiveInt                   = 64 * 1024

    # Файлы исключений
    stop_list                       : list[str]                     = Field(default_factory=list)
    add_list                        : list[str]                     = Field(default_factory=list)
    # fmt: on

    @computed_field(return_type=Path)
    @property
    def date_file(self) -> Path:
        return date_file_path()
