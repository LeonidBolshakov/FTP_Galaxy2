from datetime import date
from loguru import logger

from SRC.SYNC_APP.APP.dto import RuntimeContext, ExecutionChoice


class ExecutionGate:
    def check(self, ctx: RuntimeContext) -> ExecutionChoice:
        """
        Определяет, можно ли выполнять программу сейчас.
        """
        if not ctx.once_per_day:
            return ExecutionChoice.RUN

        file = ctx.app.date_file

        try:
            last_run = file.read_text()
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.debug(
                "Не смогли прочитать информацию из служебного файла\n"
                f"{e}\n"
                f"Выполняем запуск программы"
            )
            return ExecutionChoice.RUN

        if last_run == self._today_stamp():
            logger.info(
                "Программа сегодня уже запускалась\n"
                "Для повторного запуска удалите параметр --once_per_day\n"
                f"или файл {file.absolute()}\nили дождитесь конца суток"
            )
            return ExecutionChoice.SKIP

        return ExecutionChoice.RUN

    def record_run(self, ctx: RuntimeContext) -> None:
        """
        Записывает информацию о факте успешного запуска программы.
        """
        file = ctx.app.date_file

        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(self._today_stamp())
        except (PermissionError, OSError) as e:
            # Запуск уже произошёл, поэтому не блокируем выполнение,
            # но фиксируем проблему в логах.
            logger.error("Не смогли записать информацию в служебный файл\n" f"{e}")

    def _today_stamp(self) -> str:
        """
        Возвращает текущую дату в формате YYYY-MM-DD.
        """
        return date.today().isoformat()
