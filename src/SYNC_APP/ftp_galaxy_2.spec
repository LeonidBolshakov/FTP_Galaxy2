from PyInstaller.utils.hooks import collect_submodules, collect_data_files

rich_hiddenimports = collect_submodules("rich._unicode_data")
rich_datas = collect_data_files("rich")

a = Analysis(
    ['SRC\\SYNC_APP\\main.py'],
    pathex=[],
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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FTP_galaxy_2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FTP_galaxy_2',
)
