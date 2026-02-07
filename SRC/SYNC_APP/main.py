"""Точка входа CLI-приложения синхронизации удалённого и локального репозиториев (SYNC_APP).

Модуль инициализирует окружение выполнения, настраивает логирование, устанавливает
соединение с FTP-сервером через адаптер и запускает основной контроллер синхронизации.

Архитектура (в общих чертах):
- CLI → парсинг аргументов и загрузка конфигурации
- RuntimeContext → параметры выполнения, передаваемые в сервисы/адаптеры
- Ftp (адаптер) → обёртка над `ftplib.FTP` + единый интерфейс подключения/закрытия
- SyncController → оркестрация снимков, планирования различий, трансфера и валидации

Коды завершения:
- 0   — успешное выполнение
- 1   — ошибка выполнения (FTP/файлы/конфиг/прерывание пользователем через UI и т.п.)
- 2   — ошибка загрузки конфигурационного файла
- 130 — остановлено пользователем (Ctrl+C)
- 777 — выполнение пропущено (уже запускалось сегодня / SkipExecute)
"""

import sys
from contextlib import suppress
from datetime import date
from pathlib import Path

from SYNC_APP.CONFIG.config import SyncConfig


def _date_file_path() -> Path:
    # важно: импорт внутри — чтобы "быстрый выход" не тянул лишнее
    # date_file в той же директории, что и log
    from platformdirs import user_log_dir

    log_dir = Path(user_log_dir(appname="FTP-Galaxy2", appauthor="Bolshakov"))
    return log_dir / "date_file"


def _already_ran_today() -> bool:
    try:
        last = _date_file_path().read_text(encoding="utf-8").splitlines()[0].strip()
    except FileNotFoundError:
        return False
    except Exception:
        # если файл битый/пустой/нет доступа — лучше выполнить, чем "залипнуть" навсегда
        return False

    return last == date.today().isoformat()


def main() -> int:
    """Запуск CLI-приложения.

    Последовательность действий:
    1) Парсит аргументы командной строки.
    2) Если включён once_per_day и дата в date_file равна сегодняшней — завершает работу (777),
       не выполняя тяжёлые импорты и не подключаясь к FTP.
    3) Загружает конфигурацию приложения.
    4) Формирует RuntimeContext и настраивает логирование.
    5) Создаёт FTP-клиент (ftplib) и адаптер Ftp, подключается к серверу.
    6) Инициализирует `SyncController` со всеми сервисами и запускает run().

    Обработка ошибок:
    - Возвращает целочисленный код завершения процесса (см докстринг модуля).
    - Всегда пытается закрыть FTP-подключение в finally (ошибки закрытия подавляются).

    Returns
        int: код завершения процесса.
    """

    # Разбор аргументов CLI и загрузка config c параметрами.
    # (импортируем только то, что нужно для раннего решения "запускать/не запускать")

    from SRC.SYNC_APP.CONFIG.config_CLI import parse_args
    from SRC.GENERAL.errors import ConfigError

    try:
        args = parse_args()
    except ConfigError as e:
        print(str(e))
        return 2

    # Быстрый выход "раз в сутки" — ДО тяжёлых импортов/инициализации/FTP
    if getattr(args, "once_per_day", False) and _already_ran_today():
        return 777

    # Дальше можно тянуть всё тяжёлое
    from ftplib import FTP
    from loguru import logger
    from SRC.GENERAL.loadconfig import load_config
    from SRC.GENERAL.errors import ConfigLoadError
    from SRC.SYNC_APP.APP.SERVICES.save_service import SaveService
    from SRC.SYNC_APP.ADAPTERS.ftp import Ftp
    from SRC.SYNC_APP.APP.controller import SyncController
    from SRC.SYNC_APP.APP.SERVICES.snapshot_service import SnapshotService
    from SRC.SYNC_APP.APP.SERVICES.diff_planer import DiffPlanner
    from SRC.SYNC_APP.APP.SERVICES.transfer_service import TransferService
    from SRC.SYNC_APP.APP.SERVICES.validate_service import ValidateService
    from SRC.SYNC_APP.APP.SERVICES.repository_validator import RepositoryValidator
    from SRC.SYNC_APP.APP.SERVICES.report_service import ReportService
    from SRC.SYNC_APP.INFRA.executiongate import ExecutionGate
    from SRC.SYNC_APP.INFRA.setup_loguru import setup_loguru
    from SRC.SYNC_APP.APP.dto import (
        RuntimeContext,
        FTPInput,
    )
    from SRC.GENERAL.errors import AppError

    try:
        # Загрузка конфигурации приложения из файла.
        app = load_config(args.config, SyncConfig)
    except ConfigLoadError as e:
        # Для ошибки файла конфигурации используется отдельный код возврата.
        print(f"Ошибка файла конфигурации\n{e}")
        return 2

    # Контекст выполнения, который используется сервисами/адаптерами приложения.
    runtime = RuntimeContext(
        app=app,
        once_per_day=args.once_per_day,
        mode_stop_list=args.mode,
    )
    # Инициализация логирования на основе контекста выполнения.
    setup_loguru(config=runtime)

    # "Сырой" клиент ftplib передаётся в адаптер (упрощает единый интерфейс и тестирование).
    raw_ftp = FTP()
    ftp_client = Ftp(FTPInput(context=runtime, ftp=raw_ftp))

    try:
        ftp_client.connect()
        controller = SyncController(
            ftp=ftp_client,
            runtime_context=runtime,
            snapshot_service=SnapshotService(),
            diff_planner=DiffPlanner(),
            transfer_service=TransferService(),
            execution_gate=ExecutionGate(),
            repository_validator=RepositoryValidator(),
            validate_service=ValidateService(),
            save_service=SaveService(),
            report_service=ReportService(),
        )

        controller.run()
        return 0

    except KeyboardInterrupt:
        logger.error("Остановлено пользователем (Ctrl+C)")
        return 130

    except AppError as e:
        ret_code = getattr(e, "exit_code", 1)
        if ret_code != 777:
            logger.error("{}:\n{}", getattr(e, "log_message", "Ошибка приложения"), e)
        return ret_code

    except Exception:
        logger.exception("Непредвиденная ошибка\n")
        return 1

    finally:
        # Гарантированная попытка закрыть соединение; ошибки закрытия не должны "перебивать"
        # исходную ошибку выполнения.
        with suppress(Exception):
            ftp_client.close()


if __name__ == "__main__":
    # Сохраняем код завершения `main()` и передаём его в код завершения процесса.
    rc = main()

    # CLI-пауза: позволяет прочитать вывод при ручном запуске из окна.
    # При "пропуске" (777) пауза не нужна (типичный сценарий планировщика).
    if rc != 777:
        try:
            input("Для окончания работы нажмите ENTER")
        except KeyboardInterrupt:
            pass

    sys.exit(rc)
