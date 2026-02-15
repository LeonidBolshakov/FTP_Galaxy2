@echo off
setlocal

rem Папка где лежит батник (src\)
set "SRC_DIR=%~dp0"

rem Корень проекта (на уровень выше src)
for %%I in ("%SRC_DIR%..") do set "PROJECT_ROOT=%%~fI"

set "PY=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "SPEC=%SRC_DIR%news_digest.spec"

rem Явно задаём куда складывать сборку
set "DIST=%SRC_DIR%dist_didget"
set "WORK=%SRC_DIR%build"
set "OUT=%DIST%\news_digest"

rem Чистим ВСЮ dist, чтобы не было "третьих exe"
rmdir /s /q "%DIST%" 2>nul
rmdir /s /q "%WORK%" 2>nul

call "%PY%" -m PyInstaller -y --log-level=ERROR "%SPEC%" --clean --noconfirm --distpath "%DIST%" --workpath "%WORK%" || exit /b 1

rem Копируем yaml рядом с exe
copy /y %SRC_DIR%GENERAL\config_digest.yaml      %OUT% >nul
copy /y %SRC_DIR%GENERAL\config_descr.yaml        %OUT% >nul

echo Files in: "%OUT%"

endlocal
