"""
validate_service.py

Сервис валидации результата скачивания в директорию NEW.

Назначение:
- Сравнить план скачивания (plan.to_download) и фактическое содержимое NEW.
- Выявить:
  1) нескачанные файлы (должны быть в NEW, но их нет),
  2) лишние объекты в NEW (есть в NEW, но их нет в плане),
  3) несоответствия для общих файлов (размер и/или md5).

Результат:
- Возвращает (ok, report), где report — список ReportItem с ERROR/FATAL.
"""

from SYNC_APP.APP.dto import (
    ValidateInput,
    ReportItems,
    ReportItem,
    RepositorySnapshot,
    FileSnapshot,
    StatusReport,
)


class ValidateService:
    """Сервис проверки корректности скачивания файлов в NEW по рассчитанному плану."""

    def run(self, data: ValidateInput) -> tuple[bool, ReportItems]:
        """
        Запустить валидацию.

        Собирает:
        - plan_set: имена файлов, которые должны быть скачаны (plan.to_download).
        - new_dir_set: имена объектов, реально лежащих в NEW (iterdir()).

        Затем формирует отчёт, объединяя три проверки:
        - compare_undownloaded_files: файлы из плана, отсутствующие в NEW
        - compare_unnecessary_files: объекты в NEW, отсутствующие в плане
        - compare_common_files_size_and_hash: для общих имён — проверка size и md5 (если возможно)

        Args:
            data: ValidateInput, содержащий:
                - plan: план синхронизации (используется to_download),
                - new_dir: Path директории NEW,
                - local_snap/remote_snap: снапшоты для сравнения метаданных.

        Returns:
            tuple[bool, ReportItems]:
                ok == True  -> ошибок нет (report пуст)
                ok == False -> есть ошибки/фаталы
        """
        # Имена файлов, которые ожидаем увидеть в NEW согласно плану.
        plan_set = {item.name for item in data.plan.to_download}

        # Имена объектов, которые реально находятся в директории NEW.
        # Важно: здесь берутся ВСЕ элементы iterdir() (включая каталоги, если они есть).
        new_dir_set = {item.name for item in data.new_dir.iterdir()}

        result: ReportItems = []
        result.extend(self.compare_undownloaded_files(plan_set, new_dir_set))
        result.extend(self.compare_unnecessary_files(plan_set, new_dir_set))
        result.extend(
            self.compare_common_files_size_and_hash(
                plan_set, new_dir_set, data.local_snap, data.remote_snap
            )
        )
        return False if result else True, result

    def compare_undownloaded_files(
            self, plan_set: set[str], new_dir_set: set[str]
    ) -> ReportItems:
        """
        Найти файлы, которые планировались к скачиванию, но отсутствуют в NEW.

        Args:
            plan_set: имена файлов из плана скачивания.
            new_dir_set: имена объектов в NEW.

        Returns:
            ReportItems: список ReportItem со статусом ERROR по каждому нескачанному файлу.
        """
        result: ReportItems = list()
        undownloaded_files = plan_set - new_dir_set
        for name in sorted(undownloaded_files):
            result.append(
                ReportItem(
                    name=name,
                    status=StatusReport.ERROR,
                    comment="Файл не скачан с FTP сервера",
                )
            )

        return result

    def compare_unnecessary_files(
            self, plan_set: set[str], new_dir_set: set[str]
    ) -> ReportItems:
        """
        Найти «лишние» объекты в NEW, которых нет в плане скачивания.

        Примечание:
        - В current-логике статус FATAL: предполагается, что NEW должна содержать строго то,
          что запланировано, без посторонних файлов/папок.

        Args:
            plan_set: имена файлов из плана скачивания.
            new_dir_set: имена объектов в NEW.

        Returns:
            ReportItems: список ReportItem со статусом FATAL по каждому лишнему объекту.
        """
        result: ReportItems = list()
        unnecessary_files = new_dir_set - plan_set
        for name in sorted(unnecessary_files):
            result.append(
                ReportItem(
                    name=name,
                    status=StatusReport.FATAL,
                    comment="Лишний объект в директории NEW",
                )
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
        """
        Проверить общие файлы (присутствуют и в плане, и в NEW) по размеру и md5.

        Для каждого общего имени:
        - берём FileSnapshot из local_snap и remote_snap,
        - выполняем проверки check_size и check_md5_hash,
        - добавляем ReportItem, если проверка выявила проблему.

        Args:
            plan_set: имена файлов из плана скачивания.
            new_dir_set: имена объектов в NEW.
            local_snap: снапшот «локальной» стороны для сравнения.
            remote_snap: снапшот «удалённой» стороны для сравнения.

        Returns:
            ReportItems: список ReportItem по найденным несоответствиям.

        Raises:
            RuntimeError: если в одном из снапшотов отсутствует FileSnapshot для общего имени.
                          (Считается ошибкой согласованности входных данных.)
        """

        general_files = new_dir_set & plan_set
        result: ReportItems = list()
        for name in sorted(general_files):

            local = local_snap.files.get(name)
            remote = remote_snap.files.get(name)
            if local is None or remote is None:
                result.append(
                    ReportItem(
                        name=name,
                        status=StatusReport.ERROR,
                        comment=f"Отсутствует Snapshot: local={local is not None}, remote={remote is not None}",
                    )
                )
                raise RuntimeError(
                    f"Snapshot отсутствует для {name}: local={local is not None}, remote={remote is not None}"
                )

            # Порядок проверок фиксирован: сначала размер, затем контрольная сумма.
            for check in (self.check_size, self.check_md5_hash):
                if (item := check(local, remote, name)) is not None:
                    result.append(item)

        return result

    def check_size(
            self, local: FileSnapshot, remote: FileSnapshot, name: str
    ) -> ReportItem | None:
        """
        Проверить совпадение размера файла.

        Args:
            local: локальный снапшот файла.
            remote: удалённый снапшот файла.
            name: имя файла (для отчёта).

        Returns:
            ReportItem при несовпадении размеров, иначе None.
        """
        if local.size != remote.size:
            return ReportItem(
                name=name,
                status=StatusReport.ERROR,
                comment=f"Размер скачанного файла {local.size} "
                        f"не равен размеру оригинала {remote.size}",
            )

        return None

    def check_md5_hash(
            self, local: FileSnapshot, remote: FileSnapshot, name: str
    ) -> ReportItem | None:
        """
        Проверить совпадение md5 контрольных сумм.

        Логика:
        - Если md5 отсутствует на любой стороне — формируется ERROR о невозможности проверки.
        - Иначе сравниваются нормализованные (casefold + strip) значения.

        Args:
            local: локальный снапшот файла.
            remote: удалённый снапшот файла.
            name: имя файла (для отчёта).

        Returns:
            ReportItem при проблеме (нет md5 или несовпадение), иначе None.
        """
        missing = []
        if local.md5_hash is None:
            missing.append("Контрольная сумма скачанного файла отсутствует.")
        if remote.md5_hash is None:
            missing.append("Контрольная сумма файла на FTP отсутствует.")
        if missing:
            return ReportItem(
                name=name,
                status=StatusReport.ERROR,
                comment=" ".join(missing) + " Проверка совпадения файлов невозможна.",
            )

        l = self._norm_md5(local.md5_hash)
        r = self._norm_md5(remote.md5_hash)
        if l != r:
            return ReportItem(
                name=name,
                status=StatusReport.ERROR,
                comment=f"Контрольные суммы не совпадают (получено {l}, ожидалось {r})",
            )
        return None

    def _norm_md5(self, md5: str | None) -> str | None:
        """
        Нормализовать строку md5 для сравнения.

        Делает сравнение нечувствительным к регистру и пробельным символам по краям.

        Args:
            md5: исходная строка md5 или None.

        Returns:
            Нормализованная строка или None.
        """
        if md5 is None:
            return None
        return md5.casefold().strip()
