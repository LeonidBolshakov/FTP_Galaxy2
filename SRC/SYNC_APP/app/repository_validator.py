from SRC.SYNC_APP.app.dto import RepositorySnapshot, VersionConflictGroup


class RepositoryValidator:
    def run(self, snapshot: RepositorySnapshot) -> list[VersionConflictGroup]:
        # временная реализация: считаем, что всё корректно
        return []
