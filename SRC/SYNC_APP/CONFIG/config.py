from pathlib import Path
from typing import Optional, Literal

from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


# ----------------------------
# Logging config (для loguru)
# ----------------------------
class ConsoleLoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"


class FileLoggingConfig(BaseModel):
    level: str = "DEBUG"
    path: str = "../sync.log"
    rotation: str = "10 MB"
    format: str = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {file.name}{function}:{line} - {message}"
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
    # FTP
    ftp_host: str = "ftp.galaktika.ru"
    ftp_user: str
    ftp_root: str = "/"
    ftp_timout_sec: int = 5

    # Локальный репозиторий
    local_root: str
    staging_new: str = "NEW"
    staging_old: str = "OLD"

    # Поведение
    verify_mode: Literal["size", "file_hash"] = "size"
    conflict_policy: Literal["FAIL", "WARN"] = "FAIL"

    # Logging
    logging: LoggingConfig = LoggingConfig()

    model_config = SettingsConfigDict(
        extra="forbid",
    )


class ConfigLoadError(RuntimeError):
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
        raise ConfigLoadError(f"Не удачное чтение config файла: {cfg_path}\n{e}") from e

    try:
        raw_data = yaml.safe_load(raw_text) or {}

    except Exception as e:
        raise ConfigLoadError(f"Нарушена структура YAML файла: {cfg_path}\n{e}") from e

    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as e:
        raise ConfigLoadError(f"Неверная конфигурация в {cfg_path}:\n{e}") from e
