from datetime import date
from loguru import logger
from typing import cast
from pathlib import Path

from SYNC_APP.APP.types import ExecutionChoice
from SYNC_APP.APP.dto import RuntimeContext


class ExecutionGate:
    """
    Гейт выполнения: решает, можно ли запускать программу сейчас, и фиксирует факт запуска.

    Назначение:
        При включённом режиме `once_per_day` предотвращает повторный запуск в течение суток.
        Для этого читает/пишет служебный файл `ctx.app.date_file`, в котором хранится дата
        последнего запуска в формате `YYYY-MM-DD`.

    Примечания:
        - Логика не “блокирующая”: если служебный файл недоступен для чтения или записи,
          выполнение не запрещается (возвращается RUN), но ситуация логируется.
        - Сравнение выполняется по локальной дате системы (date.today()).
    """

    def check(self, ctx: RuntimeContext) -> ExecutionChoice:
        """
        Определяет, можно ли выполнять программу сейчас.

        Логика:
            1) Если `ctx.once_per_day == False`, всегда разрешаем запуск.
            2) Если `ctx.once_per_day == True`, читаем `ctx.app.date_file`.
               - если файл не читается (нет/нет прав/ошибка ФС) — разрешаем запуск;
               - если в файле сегодняшняя дата — запрещаем повторный запуск (SKIP);
               - иначе — разрешаем запуск (RUN).

        Args:
            ctx: Контекст выполнения с флагом `once_per_day` и путями приложения.

        Returns:
            ExecutionChoice.RUN если запуск разрешён,
            ExecutionChoice.SKIP если запуск нужно пропустить (уже был запуск сегодня).
        """
        if not ctx.once_per_day:
            return ExecutionChoice.RUN

        file = cast(Path, ctx.app.date_file)

        try:
            last_run = file.read_text().strip()
        except (FileNotFoundError, PermissionError, OSError) as e:
            # Если служебный файл недоступен — не блокируем запуск, но пишем debug.
            logger.warning(
                "Не смогли прочитать информацию из служебного файла\n"
                f"{e}\n"
                f"Выполняем запуск программы"
            )
            return ExecutionChoice.RUN

        # Если последний запуск уже был сегодня — пропускаем выполнение.
        if last_run == self._today_stamp():
            logger.info(
                "Программа сегодня уже запускалась\n"
                "Для повторного запуска удалите параметр --once_per_day\n"
                f"или файл {file.absolute()}\n"
                f"или дождитесь следующих суток"
            )
            return ExecutionChoice.SKIP

        return ExecutionChoice.RUN

    def record_run(self, ctx: RuntimeContext) -> None:
        """
        Записывает информацию о факте запуска (текущую дату) в служебный файл.

        Вызывается после успешного старта/выполнения.

        Поведение:
            - создаёт родительские директории под `ctx.app.date_file`, если нужно;
            - пишет в файл строку с сегодняшней датой в формате YYYY-MM-DD;
            - при ошибке записи НЕ поднимает исключение, а только логирует ошибку.

        Args:
            ctx: Контекст выполнения, содержащий путь `ctx.app.date_file`.
        """
        file = cast(Path, ctx.app.date_file)

        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(self._today_stamp().strip())
        except (PermissionError, OSError) as e:
            # Запуск уже произошёл, поэтому не блокируем выполнение,
            # но фиксируем проблему в логах.
            logger.error("Не смогли записать информацию в служебный файл\n" f"{e}")

    def _today_stamp(self) -> str:
        """
        Возвращает текущую дату в формате YYYY-MM-DD (ISO 8601, без времени).

        Используется как значение, хранимое в служебном файле, и как эталон для сравнения.

        Returns:
            Строка вида "2026-01-29".
        """
        return date.today().isoformat()
