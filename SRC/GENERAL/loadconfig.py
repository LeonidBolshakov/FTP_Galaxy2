from pathlib import Path
from typing import Type, TypeVar, Any

import yaml
from pydantic import BaseModel, ValidationError

from SRC.GENERAL.errors import ConfigLoadError, ConfigError

TConfig = TypeVar("TConfig", bound=BaseModel)


def _read_yaml_file(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigLoadError(f"Неудачное чтение config файла: {path}\n{e}") from e

    try:
        return yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Нарушена структура YAML файла: {path}\n{e}") from e


def _merge_shallow(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Плоское слияние словарей: ключи из override перекрывают base.
    (Как твой ранее показанный base.update(data), но без мутаций аргументов.)
    """
    merged = dict(base)
    merged.update(override)
    return merged


def load_yaml_with_include(path: Path, _stack: tuple[Path, ...] = ()) -> dict[str, Any]:
    """
    Собирает итоговый конфиг с поддержкой include.
    include может быть:
      - строкой: include: base.yaml
      - списком: include: [base.yaml, logging.yaml]
    """
    path = path.resolve()

    # защита от циклов include
    if path in _stack:
        chain = " -> ".join(str(p) for p in _stack + (path,))
        raise ConfigError(f"Циклический include в конфиге:\n{chain}")

    data = _read_yaml_file(path)

    includes = data.pop("include", None)
    if not includes:
        return data

    if isinstance(includes, str):
        includes = [includes]
    if not isinstance(includes, list) or not all(isinstance(x, str) for x in includes):
        raise ConfigError(
            f"{path}\nКлюч include должен быть строкой или списком строк (путей)."
        )

    merged: dict[str, Any] = {}
    for rel in includes:
        base_path = (path.parent / rel).resolve()
        base_data = load_yaml_with_include(base_path, _stack=_stack + (path,))
        merged = _merge_shallow(merged, base_data)

    # финальное перекрытие значениями текущего файла
    merged = _merge_shallow(merged, data)
    return merged


def load_config(path: str | Path, config_cls: Type[TConfig]) -> TConfig:
    """
    Загружает конфигурацию из YAML-файла и валидирует её через переданный Pydantic-класс.
    """
    cfg_path = Path(path)

    if cfg_path.suffix.lower() not in {".yaml", ".yml"}:
        raise ConfigLoadError(
            f"Ожидался YAML-файл конфигурации (.yaml/.yml), но получен: {cfg_path}"
        )

    if not cfg_path.exists():
        raise ConfigLoadError(f"Config файл не найден: {cfg_path}")

    try:
        raw_data = load_yaml_with_include(cfg_path)
        return config_cls.model_validate(raw_data)
    except ValidationError as e:
        raise ConfigError(f"{cfg_path}\n{e}") from e
