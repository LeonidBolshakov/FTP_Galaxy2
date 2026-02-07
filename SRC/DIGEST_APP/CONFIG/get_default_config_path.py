from pathlib import Path
import sys


def exe_dir() -> Path:
    return Path(sys.executable).resolve().parent


def dev_default_config() -> Path:
    # твой текущий путь в проекте:
    return Path(__file__).resolve().parent / "config.yaml"


def external_default_config() -> Path:
    return exe_dir() / "config.yaml"


def built_in_default_config() -> Path:
    # то, что PyInstaller положит во временную папку onefile
    base = Path(getattr(sys, "_MEIPASS", exe_dir()))
    return base / "config.yaml"  # если add-data кладём в "."


def get_default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return external_default_config()
    return dev_default_config()
