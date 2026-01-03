import sys

from loguru import logger

from SRC.SYNC_APP.app.dto import RuntimeContext


def setup(config: RuntimeContext):
    logger.remove()

    # fmt: off
    logger.add(
        sys.stderr,
        level               =config.app.logging.console.level,
        format              =config.app.logging.console.format,
        colorize            =True,
    )

    logger.add(
        config.app.logging.file.path,
        level               =config.app.logging.file.level,
        format              =config.app.logging.file.format,
        rotation            =config.app.logging.file.rotation,
        retention           =config.app.logging.file.retention,
        compression         =config.app.logging.file.compression,
        encoding            ="utf-8",
    )


# fmt: on
