from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    ValidateRepositoryInput,
    ValidateInput,
    RuntimeContext,
    ReportItemInput,
)


class EmptyRepositoryValidator:
    def run(self, data: ValidateRepositoryInput) -> list:
        logger.info(f"Validating repository")
        return list()


class ValidateAndSaveService:
    def validate(self, data: ValidateInput):
        logger.info("ValidateAndSaveService.validate")
        return True, list()

    def commit_keep_new(self, data: RuntimeContext):
        logger.info("ValidateAndSaveService.commit_keep_new")

    def commit_keep_new_old_files(self, data: RuntimeContext):
        logger.info("ValidateAndSaveService.commit_keep_new_old_files")


class ReportService:
    def run(self, data: ReportItemInput) -> None:
        logger.info("ReportService.run")
