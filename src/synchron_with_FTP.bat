@echo off
setlocal

rem Папка где лежит батник (src\)
set "SRC_DIR=%~dp0"

rem Корень проекта (на уровень выше src)
for %%I in ("%SRC_DIR%..") do set "PROJECT_ROOT=%%~fI"

set "PY=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "SPEC=%SRC_DIR%synchron_with_FTP.spec"

rem Явно задаём куда складывать сборку
set "DIST=%SRC_DIR%dist_sync"
set "WORK=%SRC_DIR%build"
set "OUT=%DIST%\FTP_galaxy_2"

rem Чистим ВСЮ dist, чтобы не было "третьих exe"
rmdir /s /q "%DIST%" 2>nul
rmdir /s /q "%WORK%" 2>nul

call "%PY%" -m PyInstaller -y --log-level=ERROR "%SPEC%" --clean --noconfirm --distpath "%DIST%" --workpath "%WORK%" || exit /b 1

rem Копируем yaml рядом с exe
copy /y %SRC_DIR%GENERAL\config_sync_prep.yaml  %OUT% >nul
copy /y %SRC_DIR%GENERAL\config_sync_descr.yaml %OUT% >nul
copy /y %SRC_DIR%GENERAL\config.yaml            %OUT% >nul

echo Files in: "%OUT%"

endlocal
