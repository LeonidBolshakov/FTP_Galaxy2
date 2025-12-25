from SRC.SYNC_APP.CONFIG import config
from SRC.SYNC_APP.CONFIG.config_CLI import parse_args
from SRC.SYNC_APP.INFRA import setup_loguru

from SRC.SYNC_APP.app.dto import RuntimeContext
from SRC.SYNC_APP.app.controller import SyncController
from SRC.SYNC_APP.app.repository_validator import RepositoryValidator
from SRC.SYNC_APP.INFRA.stubs import (
    AlwaysRunPolicy,
    EmptySnapshotService,
    EmptyDiffPlanner,
    TransferService,
    LogErrorHandler,
)


def main():
    args = parse_args()
    try:
        app = config.load_config(args.config)
    except config.ConfigLoadError as e:
        print(f"Ошибка файла конфигурации\n{e}")
        raise SystemExit(2)

    runtime = RuntimeContext(app=app, once_per_day=args.once_per_day)
    setup_loguru.setup(runtime)

    controller = SyncController(
        runtime_context=runtime,
        snapshot_service=EmptySnapshotService(),
        diff_planner=EmptyDiffPlanner(),
        transfer_service=TransferService(),
        repository_validator=RepositoryValidator(),
        error_handler=LogErrorHandler(),
        execution_policy=AlwaysRunPolicy(),
    )

    controller.run()


if __name__ == "__main__":
    main()
