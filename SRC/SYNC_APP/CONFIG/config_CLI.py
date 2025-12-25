from pathlib import Path
import argparse


def parse_args() -> argparse.Namespace:
    default_config = Path(__file__).parent / "config.yaml"
    p = argparse.ArgumentParser(prog="Sync_FTP_Galaxy")
    p.add_argument(
        "config",
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
    return p.parse_args()
