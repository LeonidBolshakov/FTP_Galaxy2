from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


def main() -> None:
    root = Path(__file__).resolve().parent

    spec = root / "ftp_galaxy_2.spec"
    cfg = root / "src" / "SYNC_APP" / "CONFIG" / "config_digest.yaml"
    dist = root / "dist"

    if not spec.exists():
        raise FileNotFoundError(f"Не найден spec: {spec}")
    if not cfg.exists():
        raise FileNotFoundError(f"Не найден config_digest.yaml: {cfg}")

    # Сборка по spec
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec)],
        cwd=root,
    )

    # Копируем конфиг рядом с exe (в dist)
    dist.mkdir(exist_ok=True)
    shutil.copy2(cfg, dist / "FTP_galaxy_2" / "config_digest.yaml")

    print("Файл exe построен!")
    print(
        rf'config_digest.yaml, используемые по умолчанию, находится - {dist}\"config_digest.yaml"'
    )


if __name__ == "__main__":
    main()
