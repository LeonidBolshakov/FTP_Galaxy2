from ftplib import FTP
import sys
from contextlib import suppress


from loguru import logger

from SRC.SYNC_APP.CONFIG import config
from SRC.SYNC_APP.CONFIG.config_CLI import parse_args
from SRC.SYNC_APP.ADAPTERS.ftp import Ftp
from SRC.SYNC_APP.APP.dto import (
    RuntimeContext,
    DownloadDirError,
    ConnectError,
    LocalFileAccessError,
    ConfigError,
    FTPInput,
)
from SRC.SYNC_APP.APP.controller import SyncController
from SRC.SYNC_APP.APP.SERVICES.snapshot_service import SnapshotService
from SRC.SYNC_APP.APP.SERVICES.diff_planer import DiffPlanner
from SRC.SYNC_APP.APP.SERVICES.transfer_service import TransferService
from SRC.SYNC_APP.APP.SERVICES.validate_service import ValidateService
from SRC.SYNC_APP.INFRA.executiongate import ExecutionGate
from SRC.SYNC_APP.INFRA.setup_loguru import setup_loguru
from SRC.SYNC_APP.INFRA.stubs import (
    RepositoryValidator,
    ReportService,
    SaveService,
)


def main() -> int:
    args = parse_args()
    try:
        app = config.load_config(args.config)
    except config.ConfigLoadError as e:
        print(f"Ошибка файла конфигурации\n{e}")
        return 2

    runtime = RuntimeContext(
        app=app,
        once_per_day=args.once_per_day,
        use_stop_list=args.mode,
    )
    setup_loguru(config=runtime)

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
        logger.error("Ошибка доступа к локальным файлам/каталогам:\n{}", e)
        return 1

    except (ConnectError, DownloadDirError) as e:
        logger.error("Ошибка в начале работы с FTP сервером:\n{}", e)
        return 1

    except ConfigError as e:
        logger.error("Ошибка в конфигурационном файле или параметрах:\n{}", e)
        return 1

    except Exception:
        logger.exception("Непредвиденная ошибка")
        return 1

    finally:
        with suppress(Exception):
            ftp_client.close()


if __name__ == "__main__":
    sys.exit(main())
