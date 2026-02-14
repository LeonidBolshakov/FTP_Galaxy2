from platformdirs import user_log_dir
from pathlib import Path
from typing import Literal, cast, Self, TypeVar, Any

from pydantic_settings import SettingsConfigDict
from pydantic import (
    model_validator,
    PositiveInt,
    PositiveFloat,
    Field,
    BaseModel,
)

# =============================================================================
# Base helpers
# =============================================================================

T = TypeVar("T", bound=BaseModel)


def merge_model_defaults(base: T, override: T | dict[str, Any] | None) -> T:
    """
    Возвращает НОВЫЙ объект модели:
    - override=None        -> глубокая копия base
    - override=BaseModel  -> base + override (по заданным полям)
    - override=dict       -> base + dict (как partial update)
    """
    if override is None:
        return base.model_copy(deep=True)

    if isinstance(override, BaseModel):
        update = override.model_dump(exclude_unset=True)
    elif isinstance(override, dict):
        update = override
    else:
        raise TypeError(f"Неподдерживаемый тип: {type(override)}")

    return base.model_copy(update=update, deep=True)


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
        "{file.path}{function}:{line} - {message}"
    )
    retention: str = "7 days"
    compression: str = "zip"

    @model_validator(mode="after")
    def _finalize(self) -> Self:
        if self.path is None and self.name is None:
            raise ValueError("Для файла журнализации не задан ни path, ни name")

        if self.path is None:
            log_dir = Path(user_log_dir(appname="FTP-Galaxy2", appauthor="Bolshakov"))
            log_dir.mkdir(parents=True, exist_ok=True)
            return self.model_copy(update={"path": log_dir / self.name})

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

    @model_validator(mode="after")
    def _require_file_log(self) -> Self:
        # файл-лог обязателен
        if self.file.path is None and self.file.name is None:
            raise ValueError("Для файла журнализации не задан ни path, ни name")
        return self

    model_config = SettingsConfigDict(
        # Запрещаем неизвестные ключи в YAML, чтобы не “проглатывать” опечатки.
        extra="forbid",
    )


class CommonConfig(BaseModel):
    local_dir: Path

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
    new_dir                         : Path | None                   = None
    old_dir                         : Path | None                   = None

    # Служебные файлы
    date_file                       : Path | None                    = None

    # Logging
    logging: LoggingConfig          = Field(default_factory=LoggingConfig)
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
            log_path = cast(Path, self.logging.file.path)
            self.date_file = log_path.parent / "date_file"
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

    @model_validator(mode="after")
    def _get_dirs(self) -> Self:
        if self.new_dir is None:
            self.new_dir = self.local_dir / "NEW"

        if self.old_dir is None:
            self.old_dir = self.local_dir / "OLD"

        return self
