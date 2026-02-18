from pathlib import Path, PurePosixPath
from typing import Literal, Self, TypeVar, Any

from loguru import logger
from pydantic_settings import SettingsConfigDict
from pydantic import (
    model_validator,
    PositiveInt,
    PositiveFloat,
    Field,
    BaseModel,
    PrivateAttr,
    computed_field,
)

from SYNC_APP.INFRA.utils import default_log_dir, date_file_path

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


class CommonConfig(BaseModel):
    model_config = SettingsConfigDict(
        # Запрещаем неизвестные ключи в YAML, чтобы не “проглатывать” опечатки.
        extra="forbid",
    )

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

    # Локальный репозиторий
    new_dir                         : Path | None                   = None
    old_dir                         : Path | None                   = None

    _date_file                      : Path=PrivateAttr()

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

    @computed_field(return_type=Path)
    @property
    def date_file(self) -> Path:
        return date_file_path()

    @property
    def new_dir_path(self) -> Path:
        """
        Возвращает путь new_dir как Path.

        Предполагается, что к моменту обращения _derive_dirs() уже установил new_dir,
        если он не был задан явно.
        """
        return Path(self.new_dir)

    @property
    def old_dir_path(self) -> Path:
        """
        Возвращает путь old_dir как Path.

        Предполагается, что к моменту обращения _derive_dirs() уже установил old_dir,
        если он не был задан явно.
        """
        return Path(self.old_dir)
