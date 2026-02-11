from pathlib import Path
import sys


def _exe_dir() -> Path:
    return Path(sys.executable).resolve().parent


def _development_default_config() -> Path:
    # твой текущий путь в проекте:
    return Path(__file__).resolve().parent / "config_digest.yaml"


def _external_default_config() -> Path:
    return _exe_dir() / "config_digest.yaml"


def get_default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return _external_default_config()
    return _development_default_config()
