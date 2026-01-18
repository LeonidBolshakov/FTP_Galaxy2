from SRC.SYNC_APP.APP.dto import (
    ValidateInput,
    ReportItems,
    ReportItem,
    RepositorySnapshot,
    FileSnapshot,
)


class ValidateService:
    def run(self, data: ValidateInput) -> ReportItems:
        plan_set = {item.name for item in data.plan.to_download}
        new_dir_set = {item.name for item in data.new_dir.iterdir()}

        result: ReportItems = []
        result.extend(self.compare_undownloaded_files(plan_set, new_dir_set))
        result.extend(self.compare_unnecessary_files(plan_set, new_dir_set))
        result.extend(
            self.compare_common_files_size_and_hash(
                plan_set, new_dir_set, data.local_snap, data.remote_snap
            )
        )
        return result

    def compare_undownloaded_files(
            self, plan_set: set[str], new_dir_set: set[str]
    ) -> ReportItems:
        result: ReportItems = list()
        undownloaded_files = plan_set - new_dir_set
        for name in sorted(undownloaded_files):
            result.append(ReportItem(name=name, comment="Файл не скачан с FTP сервера"))

        return result

    def compare_unnecessary_files(
            self, plan_set: set[str], new_dir_set: set[str]
    ) -> ReportItems:
        result: ReportItems = list()
        unnecessary_files = new_dir_set - plan_set
        for name in sorted(unnecessary_files):
            result.append(
                ReportItem(name=name, comment="Лишний объект в директории NEW")
            )

        return result

    # noinspection PyArgumentList
    def compare_common_files_size_and_hash(
            self,
            plan_set: set[str],
            new_dir_set: set[str],
            local_snap: RepositorySnapshot,
            remote_snap: RepositorySnapshot,
    ) -> ReportItems:

        general_files = new_dir_set & plan_set
        result: ReportItems = list()
        for name in sorted(general_files):

            local = local_snap.files.get(name)
            remote = remote_snap.files.get(name)
            if local is None or remote is None:
                raise RuntimeError(
                    f"Snapshot отсутствует для {name}: local={local is not None}, remote={remote is not None}"
                )

            for check in (self.check_size, self.check_md5_hash):
                if (item := check(local, remote, name)) is not None:
                    result.append(item)

        return result

    def check_size(
            self, local: FileSnapshot, remote: FileSnapshot, name: str
    ) -> ReportItem | None:
        if local.size != remote.size:
            return ReportItem(
                name=name,
                comment=f"Размер скачанного файла {local.size} "
                        f"не равен размеру оригинала {remote.size}",
            )

        return None

    def check_md5_hash(
            self, local: FileSnapshot, remote: FileSnapshot, name: str
    ) -> ReportItem | None:
        missing = []
        if local.md5_hash is None:
            missing.append("Контрольная сумма скачанного файла отсутствует.")
        if remote.md5_hash is None:
            missing.append("Контрольная сумма файла на FTP отсутствует.")
        if missing:
            return ReportItem(
                name=name,
                comment=" ".join(missing) + " Проверка совпадения файлов невозможна.",
            )

        l = self._norm_md5(local.md5_hash)
        r = self._norm_md5(remote.md5_hash)
        if l != r:
            return ReportItem(
                name=name,
                comment=f"Контрольные суммы не совпадают (получено {l}, ожидалось {r})",
            )
        return None

    def _norm_md5(self, md5: str | None) -> str | None:
        if md5 is None:
            return None
        return md5.casefold().strip()
