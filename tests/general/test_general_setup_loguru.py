import builtins

# noinspection PyProtectedMember
from GENERAL.setup_loguru import (
    _ensure_parent_dir_for_file_sink,
    _pause_until_user_confirms,
)


def test_ensure_parent_dir_for_file_sink_creates_parent(tmp_path):
    """Убедитесь, что функция _ensure_parent_dir_for_file_sink создаёт родительский каталог, если ей передан путь к файлу."""
    # Для вложенного пути, который ещё не существует
    file_path = tmp_path / "a" / "b" / "logfile.txt"
    parent = file_path.parent
    assert not parent.exists()
    # Когда мы вызываем функцию
    _ensure_parent_dir_for_file_sink(file_path)
    # Тогда родительский каталог должен существовать
    assert parent.exists() and parent.is_dir()


def test_ensure_parent_dir_for_file_sink_ignores_non_path_like():
    """Убедитесь, что объекты, не являющиеся строкой или путём, игнорируются."""

    class Dummy:
        pass

    dummy = Dummy()
    # Не должна выбрасывать исключение и не должна создавать каталоги
    _ensure_parent_dir_for_file_sink(dummy)


def test_pause_until_user_confirms_skipped_when_no_tty(monkeypatch):
    """Если стандартный ввод не является TTY, функция _pause_until_user_confirms должна сразу вернуть управление, не вызывая input()."""
    calls = []

    # Переопределяем sys.stdin.isatty так, чтобы он возвращал False
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    # Переопределяем input, чтобы сохранять аргументы при его вызове
    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: calls.append(args))
    _pause_until_user_confirms("prompt")
    # input не должен быть вызван
    assert not calls


def test_pause_until_user_confirms_prompts_on_tty(monkeypatch):
    """Если стандартный ввод является TTY, функция _pause_until_user_confirms должна вызвать input() с переданным сообщением."""
    messages: list[str] = []

    # Переопределяем sys.stdin.isatty так, чтобы он возвращал True
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def fake_input(msg):
        messages.append(msg)
        # Симулируем, что пользователь сразу нажимает Enter
        return ""

    monkeypatch.setattr(builtins, "input", fake_input)
    _pause_until_user_confirms("Hello")
    # input должен быть вызван один раз с переданным сообщением
    assert messages == ["Hello"]
