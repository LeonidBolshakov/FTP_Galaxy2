from loguru import logger

from SRC.SYNC_APP.CONFIG import config
from SRC.SYNC_APP.CONFIG.config_CLI import parse_args
from SRC.SYNC_APP.APP.dto import RuntimeContext, FTPListError, ConnectError
from SRC.SYNC_APP.APP.controller import SyncController
from SRC.SYNC_APP.APP.SERVICES.snapshot_service import SnapShotService
from SRC.SYNC_APP.INFRA.executiongate import ExecutionGate
from SRC.SYNC_APP.INFRA.stubs import (
    EmptyDiffPlanner,
    TransferService,
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

    runtime = RuntimeContext(app=app, once_per_day=args.once_per_day)

    controller = SyncController(
        runtime_context=runtime,
        snapshot_service=SnapShotService(),
        diff_planner=EmptyDiffPlanner(),
        transfer_service=TransferService(),
        error_handler=LogErrorHandler(),
        execution_gate=ExecutionGate(),
        repository_validator=EmptyRepositoryValidator(),
    )

    try:
        controller.run()
    except (ConnectError, FTPListError) as e:
        logger.error(f"Ошибка в начале работы с FTP сервером\n{e}")


if __name__ == "__main__":
    main()
