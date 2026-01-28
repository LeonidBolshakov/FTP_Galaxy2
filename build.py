from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


def main() -> None:
    root = Path(__file__).resolve().parent

    spec = root / "ftp_galaxy_2.spec"
    cfg = root / "SRC" / "SYNC_APP" / "CONFIG" / "config.yaml"
    dist = root / "dist"

    if not spec.exists():
        raise FileNotFoundError(f"Не найден spec: {spec}")
    if not cfg.exists():
        raise FileNotFoundError(f"Не найден config.yaml: {cfg}")

    # Сборка по spec
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec)],
        cwd=root,
    )

    # Копируем конфиг рядом с exe (в dist)
    dist.mkdir(exist_ok=True)
    shutil.copy2(cfg, dist / "config.yaml")

    print("Файл exe построен!")
    print(rf'config.yaml, используемые по умолчанию, находится - {dist}\"config.yaml"')


if __name__ == "__main__":
    main()
