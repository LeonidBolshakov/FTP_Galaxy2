# stubs.py
from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    ErrorEvent,
    ValidateRepositoryInput,
)


class EmptyRepositoryValidator:
    def run(self, data: ValidateRepositoryInput):
        logger.info(f"Validating repository {data.snapshot}")


class LogErrorHandler:
    def run(self, event: ErrorEvent) -> None:
        logger.error("Error {}: {}", event.code, event.details)
