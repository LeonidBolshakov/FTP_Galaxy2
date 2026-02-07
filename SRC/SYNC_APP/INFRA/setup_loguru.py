"""setup_loguru.py

Настройка логирования через Loguru.

Функция: func:`setup_loguru` сбрасывает ранее зарегистрированные sinks Loguru и
регистрирует:

- вывод в stderr (консоль);
- (опционально) вывод в файл согласно настройкам в class:`RuntimeContext`.

Если файловый sink зарегистрировать не удалось (например, нет прав, путь некорректен), функция:

1) пишет сообщение в уже настроенный консольный лог;
2) (опционально) ждёт подтверждения пользователя (Enter), если доступна
   интерактивная консоль (TTY);
3) (опционально) останавливает выполнение через исключение.

Дополнительно, при ошибке регистрации файла лога создаётся fallback-файл с
диагностикой в системном TEMP-каталоге, чтобы сообщение не потерялось в запуске из
планировщика/службы.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

from loguru import logger

from SRC.SYNC_APP.APP.dto import RuntimeContext


def _ensure_parent_dir_for_file_sink(path_like: Any) -> None:
    """Гарантирует существование директории для файлового sink.

    Работает только для путей файловой системы (str/Path). Для прочих типов
    (например, file-like объектов) ничего не делает.

    Args:
        path_like: Путь к файлу лога (или иной объект, поддерживаемый loguru).

    Returns:
        None.
    """
    if isinstance(path_like, (str, Path)):
        path = Path(path_like)
        # Для файла лога создаём родительскую директорию.
        path.parent.mkdir(parents=True, exist_ok=True)


def _pause_until_user_confirms(message: str) -> None:
    """Ставит паузу до подтверждения пользователем, если есть интерактивная консоль.

    В средах без TTY (планировщик/служба/перенаправление stdin) пауза
    будет пропущена.

    Args:
        message: Текст приглашения для пользователя.

    Returns:
        None.
    """
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input(message)
        except (EOFError, KeyboardInterrupt):
            # Если консоль недоступна или пользователь прервал ввод — выходим.
            pass


def setup_loguru(
        config: RuntimeContext,
        *,
        pause_on_file_error: bool = True,
) -> None:
    """Инициализирует Loguru на основе настроек приложения.

    Поведение:
        1) Удаляет все ранее добавленные sinks (`logger.remove()`), чтобы повторный
           вызов не дублировал вывод.
        2) Добавляет sink в `sys.stderr` с параметрами из
           `config.app.logging.console` (уровень, формат).
        3) Пытается добавить файловый sink из `config.app.logging.file`.

    При ошибке регистрации файлового sink:
        - пишет сообщение в лог (console sink уже включён),
        - записывает fallback-файл с диагностикой в TEMP,
        - (опционально) ждёт подтверждения пользователя (Enter) при наличии TTY,
        - (опционально) останавливает выполнение через исключение.

    Args:
        config: RuntimeContext с разделом `app.logging.console` и `app.logging.file`.
        pause_on_file_error: Если True — ждёт подтверждения пользователя (Enter),
            когда файловый sink не удалось зарегистрировать. Пауза выполняется
            только если доступен TTY.
            исключение, чтобы остановить программу.

    Returns:
        None. Функция настраивает глобальный singleton `logger` из Loguru.
    """
    # Сбрасываем sinks, чтобы повторная настройка не дублировала вывод.
    logger.remove()

    # fmt: off
    logger.add(
        sys.stderr,
        level               =config.app.logging.console.level,
        format              =config.app.logging.console.format,
        colorize            =True,
    )
    # fmt: on

    file_path = cast(Path, config.app.logging.file.path)

    try:
        # Проверяем/создаём директорию под файл лога (если это именно путь).
        _ensure_parent_dir_for_file_sink(file_path)

        # fmt: off
        logger.add(
            file_path,
            level               =config.app.logging.file.level,
            format              =config.app.logging.file.format,
            rotation            =config.app.logging.file.rotation,
            retention           =config.app.logging.file.retention,
            compression         =config.app.logging.file.compression,
            encoding            ="utf-8",
        )
        # fmt: on

    except (PermissionError, FileNotFoundError, OSError, ValueError, TypeError) as e:
        # Важно: консольный sink уже включён, поэтому здесь пишем именно в лог.
        logger.critical(
            "Не удалось зарегистрировать файл логирования: {path!r}\n{e}",
            path=file_path,
            e=e,
        )

        if pause_on_file_error:
            _pause_until_user_confirms(
                "Ошибка настройки логирования (см. сообщение выше). "
                "Нажмите Enter, чтобы продолжить программу..."
            )
