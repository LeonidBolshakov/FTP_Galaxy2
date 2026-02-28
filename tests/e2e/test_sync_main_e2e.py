"""End‑to‑end тест для всего приложения синхронизации.

Этот тест запускает функцию ``main()`` из ``SYNC_APP.main`` в приближённых к боевым условиях,
но с переопределёнными зависимостями (CLI, загрузка конфигурации, логирование, FTP и контроллер),
чтобы исключить реальные сетевые обращения и ввод/вывод. Таким образом проверяется, что
главная функция корректно оркестрирует все этапы: разбирает аргументы, загружает
конфигурацию, инициализирует логирование, создаёт и вызывает контроллер, и при этом
возвращает правильный код завершения.
"""

from types import SimpleNamespace
from pathlib import Path

from SYNC_APP.APP.types import ModeDiffPlan


def test_sync_main_e2e(monkeypatch, tmp_path):
    """Проверяет, что ``SYNC_APP.main.main()`` возвращает 0 и вызывает контроллер.

    В тесте создаётся минимальный YAML‑файл конфигурации, затем переопределяется
    парсер аргументов командной строки, функция загрузки конфигурации, класс FTP,
    метод ``setup_loguru`` и класс ``SyncController``. Это позволяет запустить
    ``main()`` без реальных сетевых и файловых операций, но с сохранением
    последовательности вызовов.
    """

    # --- подготовка конфигурации ---
    # директория local_dir в тестовой папке
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    # путь к YAML‑файлу конфигурации
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
local_dir: {local_dir}
ftp_root: "/"
ftp_host: ftp.galaktika.ru
ftp_timeout_sec: 1
""",
        encoding="utf-8",
    )

    # --- переопределяем parse_args так, чтобы он возвращал наш путь ---
    args = SimpleNamespace(
        config=cfg_path,
        once_per_day=False,
        mode=ModeDiffPlan.NOT_USE_STOP_LIST,
    )
    monkeypatch.setattr("SYNC_APP.CONFIG.config_CLI.parse_args", lambda: args)

    # --- перехватываем load_config, чтобы записать путь и класс, затем вызвать оригинал ---
    import GENERAL.loadconfig as glc

    orig_load_config = glc.load_config
    calls: list[tuple[Path, type]] = []

    def fake_load_config(path: Path, cls: type):
        calls.append((path, cls))
        return orig_load_config(path, cls)

    monkeypatch.setattr("GENERAL.loadconfig.load_config", fake_load_config)

    # --- переопределяем setup_loguru, чтобы не конфигурировать loguru во время теста ---
    monkeypatch.setattr(
        "GENERAL.setup_loguru.setup_loguru", lambda *args, **kwargs: None
    )

    # --- замещаем ftplib.FTP простым классом с методами connect/close ---
    class DummyFTP:
        def __init__(self, *a, **kw):
            pass

        def connect(self, *a, **kw):  # type: ignore[empty-body]
            return None

        def close(self, *a, **kw):  # type: ignore[empty-body]
            return None

    import ftplib

    monkeypatch.setattr(ftplib, "FTP", DummyFTP)

    # --- замещаем методы connect и close в адаптере Ftp, чтобы исключить сетевые вызовы ---
    monkeypatch.setattr("SYNC_APP.ADAPTERS.ftp.Ftp.connect", lambda self: None)
    monkeypatch.setattr("SYNC_APP.ADAPTERS.ftp.Ftp.close", lambda self: None)

    # --- подменяем SyncController stub‑классом, который записывает вызовы ---
    call_log: list[str] = []

    class DummyController:
        def __init__(self, *args, **kwargs):
            call_log.append("init")

        def run(self) -> None:
            call_log.append("run")

    monkeypatch.setattr("SYNC_APP.APP.controller.SyncController", DummyController)

    # --- импортируем main и запускаем ---
    from SYNC_APP import main as sync_main

    rc = sync_main.main()
    # --- проверки ---
    # main должен вернуть 0 при успешном выполнении
    assert rc == 0
    # load_config должна быть вызвана ровно один раз с нашим config и классом SyncConfig
    assert len(calls) == 1
    assert calls[0][0] == cfg_path
    assert calls[0][1].__name__ == "SyncConfig"
    # контроллер должен быть инициализирован и запущен
    assert call_log == ["init", "run"]
