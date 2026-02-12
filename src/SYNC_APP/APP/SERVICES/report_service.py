"""Сервис формирования и вывода отчёта о синхронизации.

`ReportService` отвечает за человеко-читаемый вывод результатов синхронизации:
— печатает краткое резюме (успешно/есть ошибки),
— при наличии элементов отчёта выводит таблицу с деталями,
— раскрашивает уровни статуса (`StatusReport`) через rich markup.
"""

from rich.console import Console
from rich.table import Table

from src.SYNC_APP.APP.dto import ReportItems, ReportItemInput, StatusReport


class ReportService:
    """Выводит отчёт синхронизации в консоль с форматированием Rich."""

    def run(self, data: ReportItemInput) -> None:
        """Формирует и выводит резюме + (опционально) таблицу отчёта.

        Parameters
        ----------
        data
            Входные данные: флаг успешности (`is_validate_commit`) и список элементов отчёта.

        Returns
        -----
        Метод ничего не возвращает.
        """
        valid_commit = data.is_validate_commit

        # Сортировка отчёта по имени гркппирует все сообщения о файле в одном месте.
        report = sorted(data.report, key=lambda r: r.name)

        # Фиксируем ширину консоли, чтобы таблица не "плясала" при разных терминалах.
        console = Console(width=119)

        self.output_resume(console=console, valid_commit=valid_commit, report=report)

        # Таблица выводится только если есть строки отчёта.
        if len(report) != 0:
            self.output_report(console=console, report=report)

    def output_resume(
            self, console: Console, valid_commit: bool, report: ReportItems
    ) -> None:
        """Печатает краткое резюме результата синхронизации.

        Parameters
        ----------
        console
            Экземпляр rich Console для вывода
        valid_commit
            Итоговый флаг успешности (агрегированный по этапам, как передал контроллер)
        report
            Элементы отчёта (ошибки/предупреждения/информационные сообщения).
        """
        if valid_commit:
            console.print(
                "[green]Синхронизация завершена.[/green] Репозитории синхронны"
            )
            return

        console.print("[bright_yellow]Обнаружены ошибки.[/bright_yellow]")
        return

    def output_report(self, console: Console, report: ReportItems) -> None:
        """Выводит таблицу с деталями отчёта.

        Parameters
        ----------
        console
            Экземпляр rich Console для вывода
        report
            Элементы отчёта, которые будут выведены строками таблицы.
        """
        table = self.creat_table_and_head_table(console=console)
        for row in report:
            table.add_row(row.name, self.get_formatted_status(row.status), row.comment)

        console.print(table)

    def creat_table_and_head_table(self, console: Console) -> Table:
        """Создаёт таблицу Rich и добавляет заголовки колонок.

        Parameters
        ----------
        console
            Не используется внутри метода (оставлен для совместимости сигнатуры).

        Returns
        -------
        Table
            Таблица Rich, готовая к наполнению строками.
        """
        table = Table()
        table.add_column("Name", width=30)
        table.add_column("Status", width=20)
        table.add_column("Comment", width=70)

        return table

    def get_formatted_status(self, status: StatusReport) -> str:
        """Возвращает строку статуса с rich-разметкой для цвета.

        Parameters
        ----------
        status
            Значение перечисления `StatusReport`.

        Returns
        -------
        str
            Строка вида ``[color]STATUS[/color]``.
        """
        colors = {
            StatusReport.INFO: "green",
            StatusReport.IMPORTANT_INFO: "bold green",
            StatusReport.WARNING: "bright_yellow",
            StatusReport.ERROR: "red",
            StatusReport.FATAL: "bold red",
        }
        color = colors.get(status, "bold red")

        return f"[{color}]{status.name}[/{color}]"
