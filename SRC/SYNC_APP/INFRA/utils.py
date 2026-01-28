import os, sys
from typing import TypeVar, Callable, Sequence, Mapping
from pathlib import Path
import posixpath

from SRC.SYNC_APP.APP.dto import LocalFileAccessError, ConfigError

T = TypeVar("T")


def prompt_action(menu: Sequence[str], mapping: Mapping[str, T]) -> T:
    use_msvcrt = (
            sys.platform == "win32" and sys.stdin.isatty() and not _is_pycharm_console()
    )

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
    try:
        dir_path_iter = dir_path.iterdir()
    except FileNotFoundError:
        return

    for p in dir_path_iter:
        if p.is_file():
            fs_call(p, "удаление", lambda: p.unlink(missing_ok=True))
        else:
            raise LocalFileAccessError(
                f"{p} каталог или другой объект. Переместите или удалите его"
            )


def fs_call(path: Path, action: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except PermissionError as e:
        raise LocalFileAccessError(f"Нет доступа к{path}") from e
    except OSError as e:
        raise LocalFileAccessError(
            f"Ошибка файловой системы при {action} для {path}:\n{e}"
        ) from e


def sure_same_drive(first_dir: Path, second_dir: Path) -> None:
    if first_dir.drive != second_dir.drive:
        raise ConfigError(
            f"Репозиторий {first_dir} и папка OLD {second_dir} должны находиться на одном диске"
        )


def safe_mkdir(dir_path: Path) -> None:
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def _is_pycharm_console() -> bool:
    return os.environ.get("PYCHARM_HOSTED") == "1"


def _read_char_windows(prompt: str) -> str:
    # noinspection PyCompatibility
    import msvcrt

    print(prompt, end="", flush=True)
    ch = msvcrt.getwch()
    print(ch)  # эхо
    return ch


def name_file_to_name_component(path: str) -> str:
    """Преобразует имя файла в имя компонента (ключ для stop-list).

    Идея: если имя содержит суффикс вида `_NNN` (номер релиза/версии) перед расширением,
    то этот номер отбрасывается. Пример:
    - `foo_12.zip` → `foo.zip`
    - `bar.tar.gz` → `bar.tar.gz` (если после последнего `_` нет числа)

    Parameters
    ----------
    path : str
        Путь/имя файла (используется `basename`).

    Returns
    -------
    str
        Нормализованный ключ (без хвоста `_NNN`, если он был).
    """
    stem, suffix = os.path.splitext(posixpath.basename(path))
    base, sep, tail = stem.rpartition("_")  # только последний "_"
    if sep and tail.isdigit():  # хвост = номер релиза
        stem = base

    return f"{stem}{suffix}"
