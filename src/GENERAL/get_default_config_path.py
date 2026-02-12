from pathlib import Path
import sys


def _exe_dir() -> Path:
    return Path(sys.executable).resolve().parent


def _development_default_config(config_name: str) -> Path:
    # твой текущий путь в проекте:
    return Path(__file__).resolve().parent / config_name


def _external_default_config(config_name: str) -> Path:
    return _exe_dir() / config_name


def get_default_config_path(config_name: str) -> Path:
    if getattr(sys, "frozen", False):
        return _external_default_config(config_name)
    return _development_default_config(config_name)
