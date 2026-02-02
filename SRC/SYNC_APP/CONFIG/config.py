"""
Конфигурация приложения и загрузка настроек из YAML.

Содержит:
- Pydantic-модели для настроек логирования (консоль/файл).
- Основную модель настроек приложения (AppConfig) на базе BaseSettings.
- Функцию load_config() для чтения YAML и валидации конфигурации.
"""

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
from platformdirs import user_log_dir


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
        rotation: Правило ротации (например, "1 MB", "1 day" и т.п. по правилам loguru).
        format: Формат записи в файл.
        retention: Политика хранения старых логов (опционально).
        compression: Сжатие архивов логов (опционально).
    """

    level: str = "DEBUG"
    path: Path | None = None
    rotation: str = "1 MB"
    format: str = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | "
        "{file.path}{function}:{line} - {message}"
    )
    retention: str | None = None
    compression: str | None = None


class LoggingConfig(BaseModel):
    """
    Группа настроек логирования.

    Attributes:
        console: Настройки консольного логирования.
        file: Настройки файлового логирования.
    """

    console: ConsoleLoggingConfig = ConsoleLoggingConfig()
    file: FileLoggingConfig = FileLoggingConfig()

    @model_validator(mode="after")
    def _derive_file_log_path(self) -> Self:
        """
        Если путь к лог-файлу не задан явно — используем системную
        пользовательскую директорию логов.
        """
        if self.file.path is None:
            log_dir = Path(
                user_log_dir(
                    appname="FTP-Galaxy2",
                    appauthor="Bolshakov",
                )
            )
            log_dir.mkdir(parents=True, exist_ok=True)
            self.file.path = log_dir / "sync.log"
        return self


# ----------------------------
# Основная конфигурация приложения
# ----------------------------


class AppConfig(BaseSettings):
    """
    Конфигурация приложения.

    Загружается при старте и используется как источник настроек.

    Примечание:
        new_dir и old_dir могут не задаваться в YAML — в этом случае они вычисляются
        на основе local_dir (см валидатор _derive_dirs()).
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

    # Служебные файлы
    date_file                       : Path | None                    = None

    # Logging
    logging: LoggingConfig = LoggingConfig()
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

    @model_validator(mode="after")
    def _derive_service_files(self) -> Self:
        """
        Если date_file не задан — размещаем его в директории логов.
        """
        if self.date_file is None:
            self.date_file = self.logging.file.path.parent / "date_file"
        return self

    @property
    def new_dir_path(self) -> Path:
        """
        Гарантированно возвращает путь new_dir как Path.

        Предполагается, что к моменту обращения _derive_dirs() уже установил new_dir,
        если он не был задан явно.
        """
        return cast(Path, self.new_dir)

    @property
    def old_dir_path(self) -> Path:
        """
        Гарантированно возвращает путь old_dir как Path.

        Предполагается, что к моменту обращения _derive_dirs() уже установил old_dir,
        если он не был задан явно.
        """
        return cast(Path, self.old_dir)

    model_config = SettingsConfigDict(
        # Запрещаем неизвестные ключи в YAML, чтобы не “проглатывать” опечатки.
        extra="forbid",
    )


# ----------------------------
# Загрузка конфигурации
# ----------------------------


class ConfigLoadError(RuntimeError):
    """
    Ошибка загрузки/разбора/валидации конфигурации.

    Используется как единый тип исключения для внешнего слоя приложения.
    """

    pass


def load_config(path: str | Path) -> AppConfig:
    """
    Загружает конфигурацию из YAML-файла и валидирует её через AppConfig.

    Args:
        path: Путь к YAML-файлу конфигурации (str или Path).

    Returns:
        Валидированный экземпляр AppConfig.

    Raises:
        ConfigLoadError:
            - если файл не найден;
            - если файл нельзя прочитать (ошибка ОС/доступа);
            - если YAML некорректен (ошибка парсинга/структуры);
            - если данные не проходят валидацию Pydantic (ValidationError).
    """
    cfg_path = Path(path)

    if not cfg_path.exists():
        raise ConfigLoadError(f"Config файл не найден: {cfg_path}")

    try:
        raw_text = cfg_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigLoadError(f"Неудачное чтение config файла: {cfg_path}\n{e}") from e

    try:
        # safe_load возвращает python-структуру (dict/list/str/None...). Пустой файл -> None.
        raw_data = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as e:
        # Здесь намеренно поднимается единая ошибка загрузки, чтобы не “протекали” детали yaml наружу.
        raise ConfigLoadError(f"Нарушена структура YAML файла: {cfg_path}\n{e}") from e

    try:
        # Валидация и приведение типов (в т.ч. Path, PositiveInt/PositiveFloat, Literal, вложенные модели)
        return AppConfig.model_validate(raw_data)
    except ValidationError as e:
        raise ConfigLoadError(f"Неверная конфигурация в {cfg_path}:\n{e}") from e
