from pathlib import Path
from typing import Optional, Literal

from pydantic import BaseModel, ValidationError
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
    rotation: str = "10 MB"
    format: str = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | "
        "{file.remote_full}{function}:{line} - {message}"
    )
    retention: Optional[str] = None
    compression: Optional[str] = None


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
    ftp_username                    : str                           = "anonymous"
    ftp_host                        : str                           = "ftp.galaktika.ru"
    ftp_timeout_sec                 : int                           = 5
    ftp_repeat                      : int                           = 3
    ftp_retry_delay_seconds         : int                           = 2

    # Локальный репозиторий
    local_root                      : Path
    path_new                        : Path                          = Path("NEW")
    path_old                        : Path                          = Path("OLD")

    # Поведение
    verify_mode                     : Literal["size", "md5_hash"]  = "md5_hash"
    conflict_policy                 : Literal["FAIL", "WARN"]       = "FAIL"

    # Служебные файлы
    date_file: Path = Path("date_file")

    # Logging
    logging: LoggingConfig = LoggingConfig()
    # fmt: on

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
