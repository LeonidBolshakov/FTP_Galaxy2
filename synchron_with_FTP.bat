@echo off
setlocal

rem Папка, где лежит bat/spec (теперь это корень проекта)
set "PROJECT_ROOT=%~dp0"

rem Папка исходников
set "SRC_DIR=%PROJECT_ROOT%SRC\"

set "PY=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "SPEC=%PROJECT_ROOT%synchron_with_FTP.spec"

rem dist надо положить в директорию вызова (текущую)
set "CALL_DIR=%CD%"
set "DIST=%CALL_DIR%\dist_sync"
set "WORK=%CALL_DIR%\build"
set "OUT=%DIST%\FTP_Galaxy_2\"

rmdir /s /q "%DIST%" 2>nul
rmdir /s /q "%WORK%" 2>nul

call "%PY%" -m PyInstaller -y --log-level=ERROR "%SPEC%" --clean --noconfirm --distpath "%DIST%" --workpath "%WORK%" || exit /b 1

rem Копируем yaml рядом с exe (из SRC\GENERAL\)
copy /y "%SRC_DIR%GENERAL\config_sync_prep.yaml"  "%OUT%" >nul
copy /y "%SRC_DIR%GENERAL\config_sync_descr.yaml" "%OUT%" >nul
copy /y "%SRC_DIR%GENERAL\config_descr.yaml" "%OUT%" >nul

echo Files in: "%OUT%"
endlocal
