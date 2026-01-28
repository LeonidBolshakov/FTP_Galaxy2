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
"""

from ftplib import FTP
import sys
from contextlib import suppress

from loguru import logger

from SRC.SYNC_APP.CONFIG import config
from SRC.SYNC_APP.CONFIG.config_CLI import parse_args
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
    DownloadDirError,
    ConnectError,
    LocalFileAccessError,
    ConfigError,
    FTPInput,
    UserAbend,
)


def main() -> int:
    """Запуск CLI-приложения.

    Последовательность действий:
    1) Парсит аргументы командной строки.
    2) Загружает конфигурацию приложения.
    3) Формирует RuntimeContext и настраивает логирование.
    4) Создаёт FTP-клиент (ftplib) и адаптер Ftp, подключается к серверу.
    5) Инициализирует `SyncController` со всеми сервисами и запускает run().

    Обработка ошибок:
    - Возвращает целочисленный код завершения процесса (см докстринг модуля).
    - Всегда пытается закрыть FTP-подключение в finally (ошибки закрытия подавляются).

    Returns
        int: код завершения процесса.
    """

    # Разбор аргументов CLI и загрузка cinfig c параметрами.
    args = parse_args()
    try:
        # Загрузка конфигурации приложения из файла.
        app = config.load_config(args.config)
    except config.ConfigLoadError as e:
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

    except LocalFileAccessError as e:
        logger.error("Ошибка при обращении к локальным файлам/каталогам:\n{}", e)
        return 1

    except (ConnectError, DownloadDirError) as e:
        logger.error("Ошибка в начале работы с FTP сервером:\n{}", e)
        return 1

    except ConfigError as e:
        logger.error("Ошибка в конфигурационном файле или параметрах:\n{}", e)
        return 1

    except UserAbend as e:
        logger.error("Пользователь прекратил работу:\n{}", e)
        return 1

    except Exception:
        logger.exception("Непредвиденная ошибка\n")
        return 1

    finally:
        # Гарантированная попытка закрыть соединение; ошибки закрытия не должны "перебивать"
        # исходную ошибку выполнения.
        with suppress(Exception):
            ftp_client.close()


if __name__ == "__main__":
    # Пробрасываем код завершения `main()` в код завершения процесса.
    sys.exit(main())
