from pathlib import Path
from typing import Type, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from SRC.GENERAL.errors import ConfigLoadError, ConfigError

TConfig = TypeVar("TConfig", bound=BaseModel)


def load_config(path: str | Path, config_cls: Type[TConfig]) -> TConfig:
    """
    Загружает конфигурацию из YAML-файла и валидирует её через SyncConfig.

    Args:
        path: Путь к YAML-файлу конфигурации (str или Path).
        config_cls: Класс конфигуратора

    Returns:
        Валидированный экземпляр SyncConfig.

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
        raise ConfigError(f"Нарушена структура YAML файла: {cfg_path}\n{e}") from e

    try:
        # Валидация и приведение типов (в т.ч. Path)
        return config_cls.model_validate(raw_data)
    except ValidationError as e:
        raise ConfigError(f"{cfg_path}\n{e}") from e
