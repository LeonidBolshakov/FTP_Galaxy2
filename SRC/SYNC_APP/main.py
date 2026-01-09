from loguru import logger
from ftplib import FTP

from SRC.SYNC_APP.CONFIG import config
from SRC.SYNC_APP.CONFIG.config_CLI import parse_args
from SRC.SYNC_APP.APP.dto import RuntimeContext, DownloadDirError, ConnectError
from SRC.SYNC_APP.APP.controller import SyncController
from SRC.SYNC_APP.APP.SERVICES.snapshot_service import SnapShotService
from SRC.SYNC_APP.APP.SERVICES.diff_planer import DiffPlanner
from SRC.SYNC_APP.APP.SERVICES.transfer_service import TransferService
from SRC.SYNC_APP.INFRA.executiongate import ExecutionGate
from SRC.SYNC_APP.INFRA.setup_loguru import setup_loguru
from SRC.SYNC_APP.INFRA.stubs import (
    LogErrorHandler,
    EmptyRepositoryValidator,
)


def main():
    args = parse_args()
    try:
        app = config.load_config(args.config)
    except config.ConfigLoadError as e:
        print(f"Ошибка файла конфигурации\n{e}")
        raise SystemExit(2)

    runtime = RuntimeContext(
        app=app,
        once_per_day=args.once_per_day,
        use_stop_add_lists=args.mode,
    )

    ftp_parameter = FTP()
    controller = SyncController(
        ftp_parameter=ftp_parameter,
        setup_loguru=setup_loguru,
        runtime_context=runtime,
        snapshot_service=SnapShotService(),
        diff_planner=DiffPlanner(),
        transfer_service=TransferService(),
        error_handler=LogErrorHandler(),
        execution_gate=ExecutionGate(),
        repository_validator=EmptyRepositoryValidator(),
    )

    try:
        controller.run()
        return 0
    except (ConnectError, DownloadDirError) as e:
        logger.error(f"Ошибка в начале работы с FTP сервером\n{e}")
    finally:
        if ftp_parameter is not None:
            try:
                ftp_parameter.close()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.error("Остановлено пользователем (Ctrl+C).")
        exit(130)
