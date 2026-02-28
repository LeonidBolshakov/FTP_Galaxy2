import types

from DIGEST_APP.APP import message as msg


def test_show_error_calls_messagebox(monkeypatch):
    """Функция show_error должна вызывать MessageBoxW с соответствующими флагами."""
    calls = []

    def fake_messagebox(handle, text, title, flags):
        calls.append((text, title, flags))
        return 0

    user32 = types.SimpleNamespace(MessageBoxW=fake_messagebox)
    windll = types.SimpleNamespace(user32=user32)
    # Патчим ctypes.windll на наш объект‑фейк
    monkeypatch.setattr(msg.ctypes, "windll", windll, raising=False)
    msg.show_error("oops")
    assert calls, "MessageBoxW должен был быть вызван"
    text, title, flags = calls[0]
    assert text == "oops"
    assert title == msg.TITLE
    # Проверяем, что установлен бит флага ошибки (0x10)
    assert flags & 0x10


def test_show_warning_calls_messagebox(monkeypatch):
    """Функция show_warning должна вызывать MessageBoxW с соответствующими флагами."""
    calls = []

    def fake_messagebox(handle, text, title, flags):
        calls.append((text, title, flags))
        return 0

    user32 = types.SimpleNamespace(MessageBoxW=fake_messagebox)
    windll = types.SimpleNamespace(user32=user32)
    monkeypatch.setattr(msg.ctypes, "windll", windll, raising=False)
    msg.show_warning("warn")
    assert calls
    text, title, flags = calls[0]
    assert text == "warn"
    assert title == msg.TITLE
    # Проверяем, что установлен бит флага предупреждения (0x30)
    assert flags & 0x30
