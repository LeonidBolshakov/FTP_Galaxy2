from pathlib import Path

import argparse

from src.GENERAL.errors import ConfigError
from src.SYNC_APP.APP.dto import ModeDiffPlan
from src.GENERAL.get_default_config_path import get_default_config_path

_MODE_MAP = {
    "stop-list": ModeDiffPlan.USE_STOP_LIST,
    "no-list": ModeDiffPlan.NOT_USE_STOP_LIST,
}


def mode_type(s: str) -> ModeDiffPlan:
    key = s.strip().lower()
    try:
        return _MODE_MAP[key]
    except KeyError:
        raise argparse.ArgumentTypeError(
            f"Недопустимый режим: {s!r}. Доступно: {', '.join(_MODE_MAP)}"
        )


def parse_args() -> argparse.Namespace:
    default_config = get_default_config_path()
    p = argparse.ArgumentParser(prog="Sync_FTP_Galaxy", exit_on_error=False)
    p.add_argument(
        "--config",
        type=Path,
        default=default_config,  # ← значение по умолчанию
        help="Путь к файлу конфигурации (по умолчанию: config_digest.yaml)",
    )
    p.add_argument(
        "--once-per-day",
        action="store_true",
        help="Выполнять не более одного раза в сутки",
    )
    p.add_argument(
        "--mode",
        type=mode_type,
        choices=list(_MODE_MAP.values()),
        default=ModeDiffPlan.NOT_USE_STOP_LIST,
        help="Режим diff-плана: stop-list (использовать stop список) | no-list (не использовать список)",
    )
    try:
        return p.parse_args()
    except argparse.ArgumentError as e:
        raise ConfigError(f"Ошибка в параметрах вызова прграммы\n{e}") from None
