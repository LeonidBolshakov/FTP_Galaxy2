from pathlib import Path
from typing import Literal, cast, Self

from pydantic import (
    BaseModel,
    ValidationError,
    model_validator,
    PositiveInt,
    PositiveFloat,
    Field,
)

from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


# ----------------------------
# Logging config (loguru)
# ----------------------------


class ConsoleLoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"


class FileLoggingConfig(BaseModel):
    level: str = "DEBUG"
    path: str = "../sync.log"
    rotation: str = "1 MB"
    format: str = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | "
        "{file.path}{function}:{line} - {message}"
    )
    retention: str | None = None
    compression: str | None = None


class LoggingConfig(BaseModel):
    console: ConsoleLoggingConfig = ConsoleLoggingConfig()
    file: FileLoggingConfig = FileLoggingConfig()


# ----------------------------
# Основная конфигурация приложения
# ----------------------------


class AppConfig(BaseSettings):
    """
    Конфигурация приложения.

    Загружается при старте и используется как неизменяемый источник настроек.
    """

    # fmt: off
    # FTP
    ftp_root                        : str                           = "/pub/support/galaktika/bug_fix/GAL910/UPDATES/"
    ftp_username                    : Literal["anonymous"]          = "anonymous"
    ftp_host                        : Literal["ftp.galaktika.ru"]   = "ftp.galaktika.ru"
    ftp_timeout_sec                 : PositiveFloat                 = 3
    ftp_repeat                      : PositiveInt                   = 3
    ftp_retry_delay_seconds         : PositiveFloat                 = 1
    ftp_blocksize                   : PositiveInt                   = 64 * 1024

    # Файлы исключений
    stop_list                       : list[str]                     = Field(default_factory=list)
    add_list                        : list[str]                     = Field(default_factory=list)

    # Локальный репозиторий
    local_dir                       : Path                          = Path("C:\\Дистрибутив\\PREPARE\\")
    new_dir                         : Path | None                   = None
    old_dir                         : Path | None                   = None

    # Поведение
    verify_mode                     : Literal["size", "md5_hash"]    = "md5_hash"
    conflict_policy                 : Literal["FAIL", "WARN"]        = "FAIL"

    # Служебные файлы
    date_file                       : Path                          = Path("date_file")

    # Logging
    logging: LoggingConfig = LoggingConfig()
    # fmt: on

    @model_validator(mode="after")
    def _derive_dirs(self) -> Self:
        # если new_dir/target не заданы в YAML — считаем от file_full_path
        if self.new_dir is None:
            self.new_dir = self.local_dir / "NEW"
        if self.old_dir is None:
            self.old_dir = self.local_dir / "OLD"
        return self

    @property
    def new_dir_path(self) -> Path:
        return cast(Path, self.new_dir)

    @property
    def old_dir_path(self) -> Path:
        return cast(Path, self.old_dir)

    model_config = SettingsConfigDict(
        extra="forbid",
    )


# ----------------------------
# Загрузка конфигурации
# ----------------------------


class ConfigLoadError(RuntimeError):
    """Ошибка загрузки конфигурации."""

    pass


def load_config(path: str | Path) -> AppConfig:
    """
    Загружает конфигурацию из YAML-файла.
    """
    cfg_path = Path(path)

    if not cfg_path.exists():
        raise ConfigLoadError(f"Config файл не найден: {cfg_path}")

    try:
        raw_text = cfg_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigLoadError(f"Неудачное чтение config файла: {cfg_path}\n{e}") from e

    try:
        raw_data = yaml.safe_load(raw_text) or {}
    except Exception as e:
        raise ConfigLoadError(f"Нарушена структура YAML файла: {cfg_path}\n{e}") from e

    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as e:
        raise ConfigLoadError(f"Неверная конфигурация в {cfg_path}:\n{e}") from e
