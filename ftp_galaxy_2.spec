# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files


block_cipher = None

# папка, где лежит .spec
project_root = Path(SPECPATH).resolve()

# Rich подгружает таблицы Unicode динамически через importlib -> PyInstaller их не видит.
rich_hiddenimports = collect_submodules("rich._unicode_data")
rich_datas = collect_data_files("rich")

a = Analysis(
    ['SRC/SYNC_APP/main.py'],
    pathex=[str(project_root)],   # чтобы импортировался пакет SRC
    binaries=[],
    datas=rich_datas,
    hiddenimports=rich_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='FTP_galaxy_2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # поставь False, если не нужна консоль
)
