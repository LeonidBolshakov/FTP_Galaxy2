from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    SaveInput,
    ValidateRepositoryInput,
    ReportItemInput,
)


class RepositoryValidator:
    def run(self, data: ValidateRepositoryInput) -> list:
        logger.info(f"Validating repository")
        return list()


class SaveService:
    def commit_keep_new_old_files(self, data: SaveInput):
        logger.info("SaveService.commit_keep_new_old_files")


class ReportService:
    def run(self, data: ReportItemInput) -> None:
        logger.info("ReportService.run")
