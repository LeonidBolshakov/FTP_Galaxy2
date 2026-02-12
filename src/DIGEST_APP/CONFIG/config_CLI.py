from pathlib import Path

import argparse

from GENERAL.get_default_config_path import get_default_config_path
from GENERAL.errors import ConfigError


def parse_args() -> argparse.Namespace:
    default_config = get_default_config_path()
    p = argparse.ArgumentParser(prog="Didgest_FTP_Galaxy", exit_on_error=False)
    p.add_argument(
        "--config",
        type=Path,
        default=default_config,  # ← значение по умолчанию
        help="Путь к файлу конфигурации (по умолчанию: config_digest.yaml)",
    )
    try:
        return p.parse_args()
    except argparse.ArgumentError as e:
        raise ConfigError(f"Ошибка в параметрах вызова прграммы\n{e}") from None
