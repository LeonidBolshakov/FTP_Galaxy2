from pathlib import Path
import sys

import argparse

from GENERAL.errors import ConfigError
from SYNC_APP.APP.types import ModeDiffPlan

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


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent  # папка exe
    return Path.cwd()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="Sync_FTP_Galaxy", exit_on_error=False)
    p.add_argument(
        "config",
        type=Path,
        help="Путь к файлу конфигурации (обязательный)",
    )
    p.add_argument(
        "--once-per-day",
        action="store_true",
        help="Выполнять не более одного раза в сутки",
    )
    p.add_argument(
        "--mode",
        type=mode_type,
        default=ModeDiffPlan.NOT_USE_STOP_LIST,
        help="Режим diff-плана: stop-list | no-list",
    )
    try:
        return p.parse_args()
    except argparse.ArgumentError as e:
        raise ConfigError(f"Ошибка параметров запуска:\n{e}") from None
