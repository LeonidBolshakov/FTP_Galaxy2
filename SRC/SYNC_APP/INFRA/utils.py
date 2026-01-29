"""
Утилиты для консольного взаимодействия и безопасных операций с файловой системой.

Модуль содержит:
- prompt_action(): вывод меню и запрос выбора (одним символом) с учётом особенностей Windows-консоли.
- clean_dir(): очистка директории от файлов (без рекурсивного удаления подпапок).
- fs_call(): единая обёртка над файловыми операциями для нормализации исключений.
- sure_same_drive(): проверка, что каталоги находятся на одном диске (актуально для Windows).
- safe_mkdir(): создание директории с parents=True, exist_ok=True.
- name_file_to_name_component(): нормализация имени файла для сопоставления со stop-list (убирает хвост вида _NNN).
"""

import os, sys
from typing import TypeVar, Callable, Sequence, Mapping
from pathlib import Path

from SRC.SYNC_APP.APP.dto import LocalFileAccessError, ConfigError

T = TypeVar("T")


def prompt_action(menu: Sequence[str], mapping: Mapping[str, T]) -> T:
    """Показывает пользователю меню и возвращает выбранное действие.

    На Windows при запуске в реальной консоли пытается читать ввод *по одному символу*
    через `msvcrt.getwch()` (без необходимости нажимать Enter). В PyCharm-консоли
    и на других платформах используется обычный `input()`.

    Поведение выбора:
    - берётся первая буква введённого (или нажатого) символа;
    - приводится к нижнему регистру;
    - ищется в `mapping`;
    - при неудаче выводится "Неверный выбор." и запрос повторяется.

    Args:
        menu: Строки меню, которые будут выведены через print() построчно.
        mapping: Сопоставление ключа (обычно одной буквы) и возвращаемого результата.

    Returns:
        Значение из `mapping`, соответствующее выбранному ключу.
    """
    # Используем msvcrt только в Windows, только в TTY, и только если это не консоль PyCharm.
    use_msvcrt = (
            sys.platform == "win32" and sys.stdin.isatty() and not _is_pycharm_console()
    )

    # В Windows читаем один символ; иначе — строку целиком через input().
    read = _read_char_windows if use_msvcrt else input

    for string in menu:
        print(string)
    while True:
        raw = read("> ").strip()
        key = raw[:1].lower() if raw else ""
        action = mapping.get(key)
        if action is not None:
            return action
        print("Неверный выбор.")


def clean_dir(dir_path: Path) -> None:
    """Удаляет все файлы в директории `dir_path`.

    Важно:
        - Если директория не существует — функция молча завершится.
        - Если внутри есть НЕ файл (например, подпапка) — выбрасывается LocalFileAccessError.
          То есть удаление НЕ рекурсивное и НЕ удаляет каталоги.

    Args:
        dir_path: Директория, которую нужно очистить от файлов.
    """
    try:
        dir_path_iter = dir_path.iterdir()
    except FileNotFoundError:
        # Нет директории — нечего очищать.
        return

    for p in dir_path_iter:
        if p.is_file():
            # Удаление файла заворачиваем в fs_call для единообразных ошибок.
            fs_call(p, "удаление", lambda: p.unlink(missing_ok=True))
        else:
            # Любой не-файл (директория, ссылка, спец объект) считаем ошибкой, чтобы
            # не удалить что-то неожиданное и не “оставить мусор” тихо.
            raise LocalFileAccessError(
                f"{p} каталог или другой объект. Переместите или удалите его"
            )


def fs_call(path: Path, action: str, fn: Callable[[], T]) -> T:
    """Выполняет файловую операцию `fn()` и преобразует ошибки ОС в LocalFileAccessError.

    Args:
        path: Путь, для которого выполняется действие (используется в тексте ошибок).
        action: Короткое описание операции (например, "удаление", "создание", "чтение").
        fn: Функция без аргументов, выполняющая реальную операцию.

    Returns:
        Результат `fn()`.

    Raises:
        LocalFileAccessError: При PermissionError или любом OSError.
    """
    try:
        return fn()
    except PermissionError as e:
        # Отдельно ловим PermissionError, чтобы дать более понятное сообщение.
        raise LocalFileAccessError(f"Нет доступа к {path}") from e
    except OSError as e:
        # Остальные ошибки файловой системы (например, “device not ready”, “invalid name” и т.п.)
        raise LocalFileAccessError(
            f"Ошибка файловой системы при {action} для {path}:\n{e}"
        ) from e


def sure_same_drive(first_dir: Path, second_dir: Path) -> None:
    """Проверяет, что два пути находятся на одном диске (актуально для Windows).

    Используется для сценариев, где важно, чтобы операции (например, rename/move)
    могли выполняться атомарно/быстро в пределах одного тома.

    Args:
        first_dir: Первый путь (обычно репозиторий/база).
        second_dir: Второй путь (например, папка OLD).

    Raises:
        ConfigError: Если `first_dir.drive != second_dir.drive`.
    """
    if first_dir.drive != second_dir.drive:
        raise ConfigError(
            f"Репозиторий {first_dir} и папка OLD {second_dir} должны находиться на одном диске"
        )


def safe_mkdir(dir_path: Path) -> None:
    """Создаёт директорию и родителей, если их нет.

    Args:
        dir_path: Путь к директории для создания.
    """
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def _is_pycharm_console() -> bool:
    """Возвращает True, если код запущен внутри PyCharm (по env-флагу)."""
    return os.environ.get("PYCHARM_HOSTED") == "1"


def _read_char_windows(prompt: str) -> str:
    """Читает один символ из консоли Windows (msvcrt), печатает эхо и возвращает символ.

    Примечание:
        Функция рассчитана на реальную Windows-консоль; в PyCharm-консоли msvcrt часто
        ведёт себя иначе, поэтому в prompt_action() она отключается через _is_pycharm_console().

    Args:
        prompt: Строка приглашения (например, "> ").

    Returns:
        Один введённый символ (строка длины 1).
    """
    # noinspection PyCompatibility
    import msvcrt

    print(prompt, end="", flush=True)
    ch = msvcrt.getwch()
    print(ch)  # эхо
    return ch


def name_file_to_name_component(name: str) -> str:
    """Преобразует имя файла в имя компонента.

    Идея: если имя содержит суффикс вида `_NNN` (номер релиза/версии) перед расширением,
    то этот номер отбрасывается.

    Примеры:
        - `foo_12.zip` → `foo.zip`
        - `bar.tar.gz` → `bar.tar.gz` (если после последнего `_` нет числа)
        - `abc_007.txt` → `abc.txt`

    Args:
        name: Имя файла.

    Returns:
        Нормализованное имя (без хвоста `_NNN`, если он был).
    """
    stem, suffix = os.path.splitext(name)
    base, sep, tail = stem.rpartition("_")  # только последний "_"
    if sep and tail.isdigit():  # хвост = номер релиза
        stem = base

    return f"{stem}{suffix}"
