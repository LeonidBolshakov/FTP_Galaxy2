from pathlib import Path

import argparse

from SRC.SYNC_APP.APP.dto import ModeDiffPlan

_MODE_MAP = {
    "stop-add": ModeDiffPlan.USE_STOP_ADD_LISTS,
    "no-lists": ModeDiffPlan.NOT_USE_STOP_ADD_LISTS,
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
    default_config = Path(__file__).parent / "config.yaml"
    p = argparse.ArgumentParser(prog="Sync_FTP_Galaxy")
    p.add_argument(
        "--config",
        type=Path,
        nargs="?",  # ← делает аргумент необязательным
        default=default_config,  # ← значение по умолчанию
        help="Путь к файлу конфигурации (по умолчанию: config.yaml)",
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
        default=ModeDiffPlan.USE_STOP_ADD_LISTS,
        help="Режим diff-плана: stop-add (использовать stop/add списки) | no-lists (не использовать списки)",
    )
    return p.parse_args()
