"""Тесты для модуля FTP (SYNC_APP.ADAPTERS.ftp).

В этом файле реализован набор тестов, покрывающий основные ветви
клиента FTP. Все комментарии и докстринги на русском языке для
наглядности. Для имитации работы сервера используются фиктивные
объекты и переопределения методов. Тесты не требуют реального
сетевого соединения.
"""

import io
from types import SimpleNamespace

import pytest
from ftplib import error_perm, error_reply, error_temp

# noinspection PyProtectedMember
from SYNC_APP.ADAPTERS.ftp import (
    Ftp,
    _RetrWriterWithProgress,
)
from SYNC_APP.APP.dto import (
    FileSnapshot,
    DownloadDirFtpInput,
    ModeSnapshot,
)
from GENERAL.errors import ConnectError, DownloadDirError, DownloadFileError


class DummyApp:
    """Минимальный набор настроек приложения для тестов."""

    ftp_blocksize = 1024  # размер блока при скачивании
    ftp_repeat = 3  # количество повторов для временных ошибок
    ftp_retry_delay_seconds = 0  # интервал между повторами (0 для ускорения тестов)
    ftp_host = "localhost"
    ftp_timeout_sec = 1
    ftp_username = "user"
    ftp_root = ""


class DummyContext:
    """Контекст, содержащий приложение с настройками."""

    app = DummyApp()


def _make_dummy_ftp_input(ftp: object) -> SimpleNamespace:
    """Создаёт объект FTPInput с фиктивным FTP и контекстом.

    Параметры
    ----------
    ftp : object
        Экземпляр, реализующий методы FTP-протокола (connect, login, cwd и др.).

    Возвращает
    ---------
    SimpleNamespace
        Пространство имён с полями `ftp` и `context` для инициализации Ftp.
    """

    return SimpleNamespace(ftp=ftp, context=DummyContext())


class DummyFTP:
    """Простейший FTP-объект, который можно переопределять в тестах.

    Атрибуты этого класса переопределяются непосредственно в тестах для
    эмуляции разных сценариев. Если метод не переопределён, вызов ничего
    не делает и возвращает None.
    """

    def __init__(self):
        pass

    def connect(
            self, host: str, timeout: float
    ):  # pragma: no cover - поведение задаётся в тестах
        return None

    def login(self, user: str, passwd: str):  # pragma: no cover
        return None

    def cwd(self, folder: str):  # pragma: no cover
        return None

    def mlsd(self):  # pragma: no cover
        return []

    def retrbinary(
            self, command: str, callback, rest=None, blocksize=8192
    ):  # pragma: no cover
        return "226"

    def sendcmd(self, cmd: str):  # pragma: no cover
        return ""

    def quit(self):  # pragma: no cover
        return None

    def close(self):  # pragma: no cover
        return None


def test_safe_size_and_get_size():
    """Проверяет, что методы _safe_size и _get_size работают корректно."""
    ftp = object.__new__(Ftp)
    # _safe_size возвращает исходный размер или 0 при None
    assert ftp._safe_size(None) == 0
    assert ftp._safe_size(42) == 42
    # _get_size извлекает целое число из поля facts['size']
    assert ftp._get_size({"size": "10"}) == 10
    # нецелое значение приводит к None
    assert ftp._get_size({"size": "abc"}) is None
    # отсутствие ключа size приводит к None
    assert ftp._get_size({}) is None


def test__ftp_call_success():
    """_ftp_call возвращает результат действия без ошибок."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    result = client._ftp_call(
        lambda: "OK",
        what="успешный вызов",
        err_cls=ConnectError,
        temp_log="tmp",
    )
    assert result == "OK"


def test__ftp_call_temporary_error_with_retry():
    """_ftp_call повторяет вызов при временной ошибке и возвращает результат."""
    calls = {"count": 0}

    def action():
        calls["count"] += 1
        if calls["count"] < 2:
            raise error_temp("temporary")
        return "result"

    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    # Подменяем обработчик временной ошибки, чтобы избежать реального reconnect
    client._handle_temporary_ftp_error = lambda temp_log, e: None
    client._sleep_retry_delay = lambda: None
    result = client._ftp_call(
        action,
        what="тест временной ошибки",
        err_cls=ConnectError,
        temp_log="tmp",
    )
    assert result == "result"
    assert calls["count"] == 2


@pytest.mark.parametrize("exc", [error_perm("550 no perm"), error_reply("500 broken")])
def test__ftp_call_permanent_error(exc):
    """Постоянные ошибки сразу переводятся в ConnectError."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    with pytest.raises(ConnectError):
        client._ftp_call(
            lambda: (_ for _ in ()).throw(exc),
            what="проверка постоянной ошибки",
            err_cls=ConnectError,
            temp_log="tmp",
        )


def test__ftp_call_unknown_error():
    """Неизвестные исключения переводятся в ConnectError."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    with pytest.raises(ConnectError):
        client._ftp_call(
            lambda: (_ for _ in ()).throw(ValueError("bad")),
            what="неизвестная ошибка",
            err_cls=ConnectError,
            temp_log="tmp",
        )


def test__ftp_call_retry_exhaustion():
    """По истечении количества повторов _ftp_call поднимает ConnectError."""

    # Создаём приложение, которое позволит всего две попытки
    class RetryApp(DummyApp):
        ftp_repeat = 2

    class RetryContext:
        app = RetryApp()

    ftp_input = SimpleNamespace(ftp=None, context=RetryContext())
    client = Ftp(ftp_input)
    # Подменяем обработчики, чтобы не переподключаться и не спать
    client._handle_temporary_ftp_error = lambda temp_log, e: None
    client._sleep_retry_delay = lambda: None
    attempts = {"count": 0}

    def action():
        attempts["count"] += 1
        # Используем timeout как временную ошибку
        from socket import timeout  # локальный импорт

        raise timeout("timeout")

    with pytest.raises(ConnectError):
        client._ftp_call(
            action,
            what="истечение повторов",
            err_cls=ConnectError,
            temp_log="tmp",
        )
    # Должно быть ровно две попытки
    assert attempts["count"] == RetryApp.ftp_repeat


def test_safe_login_handles_530_and_other_error_perm():
    """_safe_login корректно обрабатывает ответ 530 и другие error_perm."""

    # Случай: FTP возвращает 530 — сообщение должно содержать '530'
    class FtpStub530(DummyFTP):
        def login(self, user: str, passwd: str):  # noqa: D401
            raise error_perm("530 invalid credentials")

    ftp_input = _make_dummy_ftp_input(FtpStub530())
    client = Ftp(ftp_input)
    with pytest.raises(ConnectError) as err:
        client._safe_login("user")
    assert "530" in str(err.value)

    # Случай: другой error_perm (550) — просто ConnectError
    class FtpStub550(DummyFTP):
        def login(self, user: str, passwd: str):  # noqa: D401
            raise error_perm("550 some error")

    ftp_input2 = _make_dummy_ftp_input(FtpStub550())
    client2 = Ftp(ftp_input2)
    with pytest.raises(ConnectError):
        client2._safe_login("user")


def test_build_dir_items_filters_and_hash():
    """_build_dir_items фильтрует файлы и запрашивает хэши в нужном режиме."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    # Подменяем методы получения размера и хэша
    client._get_size = lambda facts: int(facts["size"]) if "size" in facts else None
    client._get_hmd5 = lambda remote, mode: (
        "md5hash" if mode == ModeSnapshot.FULL_MODE else None
    )
    raw_items = [
        ("file1.txt", {"type": "file", "size": "10"}),
        ("dir", {"type": "dir", "size": "20"}),
        ("file2.txt", {"type": "file", "size": "20"}),
    ]
    # Режим FULL_MODE: оба файла должны иметь хэш
    data_full = DownloadDirFtpInput(only_for=None, hash_mode=ModeSnapshot.FULL_MODE)
    repo_full = client._build_dir_items(raw_items, "/root", data_full)
    assert set(repo_full.files.keys()) == {"file1.txt", "file2.txt"}
    assert all(snap.md5_hash == "md5hash" for snap in repo_full.files.values())
    # Режим LITE_MODE: md5_hash не должен запрашиваться
    data_lite = DownloadDirFtpInput(
        only_for=["file2.txt"], hash_mode=ModeSnapshot.LITE_MODE
    )
    repo_lite = client._build_dir_items(raw_items, "/root", data_lite)
    assert list(repo_lite.files.keys()) == ["file2.txt"]
    assert repo_lite.files["file2.txt"].md5_hash is None


def test_calc_offset(tmp_path):
    """_calc_offset корректно определяет смещение докачки по локальному файлу."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    file_path = tmp_path / "file.bin"
    # файл не существует
    assert client._calc_offset(file_path, 100) == 0
    # файл меньше ожидаемого
    file_path.write_bytes(b"x" * 50)
    assert client._calc_offset(file_path, 100) == 50
    # файл больше ожидаемого
    file_path.write_bytes(b"x" * 200)
    assert client._calc_offset(file_path, 100) == 0


def test_download_file_branches(tmp_path):
    """download_file обрабатывает разные ситуации: неизвестный размер и совпадение размеров."""
    ftp = DummyFTP()
    ftp_input = _make_dummy_ftp_input(ftp)
    client = Ftp(ftp_input)
    # Подменяем _download_file_with_resume, чтобы он ничего не делал
    client._download_file_with_resume = lambda snapshot, local_full_path, offset: None
    # Неизвестный размер сразу приводит к DownloadFileError
    snap_unknown = FileSnapshot(name="foo.bin", size=None, md5_hash=None)
    with pytest.raises(DownloadFileError):
        client.download_file(snap_unknown, tmp_path / "foo.bin")
    # Если размер локального файла совпадает с удалённым, скачивание не выполняется
    local_path = tmp_path / "bar.bin"
    local_path.write_bytes(b"x" * 10)
    snap_same = FileSnapshot(name="bar.bin", size=10, md5_hash=None)
    # Метод должен завершиться без исключений
    client.download_file(snap_same, local_path)


def test_writer_progress_print_and_finish(capsys):
    """Проверяет счётчик скачанных байт и вывод финального сообщения."""
    f = io.BytesIO()
    writer = _RetrWriterWithProgress(
        f=f, label="file", downloaded=0, update_every_sec=0
    )
    writer(b"abc")
    assert writer.downloaded == 3
    writer.finish()
    # Проверяем, что сообщение напечатано (выводим только последнюю строку)
    captured = capsys.readouterr()
    assert "file" in captured.out


def test_ftp_call_no_reconnect():
    """При do_reconnect=False _ftp_call не вызывает переподключение."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    # Ограничиваем количество повторов до 2, чтобы тест работал быстро
    client.ftp_input.context.app.ftp_repeat = 2
    called = {"reconnect": 0, "sleep": 0}

    def fake_handle(temp_log: str, exc: BaseException) -> None:
        called["reconnect"] += 1
        return None

    def fake_sleep() -> None:
        called["sleep"] += 1

    client._handle_temporary_ftp_error = fake_handle
    client._sleep_retry_delay = fake_sleep

    attempts = {"count": 0}

    def action():
        attempts["count"] += 1
        from socket import timeout

        raise timeout("timeout")

    with pytest.raises(ConnectError):
        client._ftp_call(
            action,
            what="нет переподключения",
            err_cls=ConnectError,
            temp_log="tmp",
            do_reconnect=False,
        )
    # _handle_temporary_ftp_error не должен был вызываться
    assert called["reconnect"] == 0
    # _sleep_retry_delay вызывается столько раз, сколько попыток
    assert called["sleep"] == client.ftp_input.context.app.ftp_repeat
    assert attempts["count"] == client.ftp_input.context.app.ftp_repeat


def test_connect_success_and_failure():
    """_safe_connect вызывает метод connect FTP и обрабатывает ошибки."""

    # Успешное подключение
    class GoodFTP(DummyFTP):
        def __init__(self):
            super().__init__()
            self.connected = False

        def connect(self, host: str, timeout: float):
            self.connected = True
            return None

    good_ftp = GoodFTP()
    ftp_input = _make_dummy_ftp_input(good_ftp)
    client = Ftp(ftp_input)
    # Переопределяем _ftp_call, чтобы не вызывать оригинальный механизм повторов
    client._safe_connect("localhost", 1)
    assert good_ftp.connected

    # Подключение с ошибкой: permanent error -> ConnectError
    class BadFTP(DummyFTP):
        def connect(self, host: str, timeout: float):  # noqa: D401
            raise error_perm("550 cannot connect")

    bad_ftp = BadFTP()
    ftp_input2 = _make_dummy_ftp_input(bad_ftp)
    client2 = Ftp(ftp_input2)
    with pytest.raises(ConnectError):
        client2._safe_connect("localhost", 1)


def test_safe_cwd_ftp_and_mlsd():
    """_safe_cwd_ftp и _safe_mlsd используют _ftp_call для обработки ошибок."""

    # успешный переход
    class FTPDir(DummyFTP):
        def __init__(self):
            super().__init__()
            self.cwd_called = False
            self.mlsd_called = False

        def cwd(self, folder: str):
            self.cwd_called = True
            return None

        def mlsd(self):
            self.mlsd_called = True
            return [("f.txt", {"type": "file", "size": "1"})]

    ftp = FTPDir()
    ftp_input = _make_dummy_ftp_input(ftp)
    client = Ftp(ftp_input)
    client._safe_cwd_ftp("/")
    assert ftp.cwd_called
    items = client._safe_mlsd()
    assert ftp.mlsd_called
    assert isinstance(items, list)

    # переход с постоянной ошибкой
    class FTPDirBad(DummyFTP):
        def cwd(self, folder: str):  # noqa: D401
            raise error_perm("550 no access")

    ftp2 = FTPDirBad()
    ftp_input2 = _make_dummy_ftp_input(ftp2)
    client2 = Ftp(ftp_input2)
    with pytest.raises(DownloadDirError):
        client2._safe_cwd_ftp("/")

    # mlsd с постоянной ошибкой
    class FTPMLSDbad(DummyFTP):
        def mlsd(self):  # noqa: D401
            raise error_perm("550 bad")

    ftp3 = FTPMLSDbad()
    ftp_input3 = _make_dummy_ftp_input(ftp3)
    client3 = Ftp(ftp_input3)
    with pytest.raises(DownloadDirError):
        client3._safe_mlsd()


def test_make_safe_dir_name(tmp_path):
    """_make_safe_dir_name создаёт родительский каталог, если его нет."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    target = tmp_path / "nested" / "file.txt"
    # Удаляем родительскую директорию, чтобы проверить создание
    parent_dir = target.parent
    if parent_dir.exists():
        import shutil

        shutil.rmtree(parent_dir)
    # Вызываем метод и проверяем, что директория создана
    created_parent = client._make_safe_dir_name(target)
    assert created_parent.exists()
    assert created_parent == parent_dir.resolve()


def test_try_resume_after_failure(tmp_path):
    """_try_resume_after_failure корректно обрабатывает разные сценарии докачки."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    # Неизвестный размер всегда вызывает DownloadFileError
    snap_unknown = FileSnapshot(name="file.bin", size=None, md5_hash=None)
    with pytest.raises(DownloadFileError):
        client._try_resume_after_failure(
            snapshot=snap_unknown,
            local_path=tmp_path / "file.bin",
            cause=DownloadFileError("fail"),
        )

    # Известный размер, но offset <= 0 => проброс cause
    class Cause(Exception):
        pass

    snap_known = FileSnapshot(name="file.bin", size=10, md5_hash=None)
    # Подменяем _calc_offset возвращать 0
    client._calc_offset = lambda path, size: 0
    with pytest.raises(Cause):
        client._try_resume_after_failure(
            snapshot=snap_known,
            local_path=tmp_path / "file.bin",
            cause=Cause("origin"),
        )
    # Известный размер и offset > 0 => вызывается _download_attempt_as_download_error
    called = {"resume": False}
    client._calc_offset = lambda path, size: 5
    client._download_attempt_as_download_error = (
        lambda remote_full_name=None, local_full_name=None, offset=None: called.update(
            {"resume": True}
        )
    )
    client._try_resume_after_failure(
        snapshot=snap_known,
        local_path=tmp_path / "file.bin",
        cause=DownloadFileError("fail"),
    )
    assert called["resume"]


def test_download_file_with_resume_errors(tmp_path):
    """_download_file_with_resume делегирует докачку при ошибке загрузки."""
    ftp_input = _make_dummy_ftp_input(None)
    client = Ftp(ftp_input)
    snap = FileSnapshot(name="file.bin", size=10, md5_hash=None)
    # _download_attempt выбрасывает DownloadFileError
    client._download_attempt = lambda file_name, local_full_path, offset: (
        _ for _ in ()
    ).throw(DownloadFileError("fail"))
    called = {"resume": False}
    client._try_resume_after_failure = (
        lambda snapshot, local_path, cause: called.update({"resume": True})
    )
    client._download_file_with_resume(snap, tmp_path / "file.bin")
    assert called["resume"]


def test_get_hmd5_modes_and_errors():
    """_get_hmd5 возвращает None в LITE_MODE и парсит ответ XMD5 в FULL_MODE."""

    # Фиктивный FTP, возвращающий корректный ответ
    class FTPXMD5(DummyFTP):
        def __init__(self):
            super().__init__()
            self.sent = []

        def sendcmd(self, cmd: str) -> str:  # noqa: D401
            self.sent.append(cmd)
            # Возвращаем строку, где MD5 — последнее слово
            return "213 0 abcdef123456"

    ftp = FTPXMD5()
    ftp_input = _make_dummy_ftp_input(ftp)
    client = Ftp(ftp_input)
    # В режиме LITE хэш не запрашивается
    assert client._get_hmd5("file.txt", ModeSnapshot.LITE_MODE) is None
    # В режиме FULL вызывается XMD5
    md5 = client._get_hmd5("file.txt", ModeSnapshot.FULL_MODE)
    assert md5 == "abcdef123456"
    assert ftp.sent[-1].startswith("XMD5")

    # Неправильный/пустой ответ приводит к DownloadDirError
    class FTPBadXMD5(DummyFTP):
        def sendcmd(self, cmd: str) -> str:  # noqa: D401
            return ""  # пустая строка

    ftp_bad = FTPBadXMD5()
    ftp_input2 = _make_dummy_ftp_input(ftp_bad)
    client2 = Ftp(ftp_input2)
    with pytest.raises(DownloadDirError):
        client2._get_hmd5("file.txt", ModeSnapshot.FULL_MODE)


def test_reconnect_failure():
    """_reconnect выбрасывает ConnectError при невозможности переподключиться."""

    class BadFTP(DummyFTP):
        def __init__(self):
            super().__init__()
            self.close_called = False

        def connect(self, host: str, timeout: float):  # noqa: D401
            raise error_temp("cannot connect")

    bad_ftp = BadFTP()
    ftp_input = _make_dummy_ftp_input(bad_ftp)
    client = Ftp(ftp_input)
    # Патчим FTP в модуле адаптера, чтобы избежать реального подключения
    from SYNC_APP.ADAPTERS import ftp as ftp_module  # type: ignore

    orig_ftp_cls = ftp_module.FTP

    # Новый класс возвращает объект, чей connect бросает временную ошибку
    class StubFTP:
        def __init__(self):
            pass

        def close(self):  # pragma: no cover
            pass

        def connect(self, host: str = "", timeout: float = 0.0):  # noqa: D401
            raise error_temp("cannot connect")

        def login(self, user: str = "", passwd: str = ""):  # pragma: no cover
            pass

        def cwd(self, folder: str = ""):  # pragma: no cover
            pass

    ftp_module.FTP = StubFTP
    try:
        with pytest.raises(ConnectError):
            client._reconnect()
    finally:
        # Восстанавливаем исходный класс FTP
        ftp_module.FTP = orig_ftp_cls


def test_close_quiet():
    """close должен молча проглатывать исключения в quit и close."""

    class BadFTP(DummyFTP):
        def quit(self):  # noqa: D401
            raise Exception("quit failed")

        def close(self):  # noqa: D401
            raise Exception("close failed")

    ftp = BadFTP()
    ftp_input = _make_dummy_ftp_input(ftp)
    client = Ftp(ftp_input)
    # close не должен поднимать исключений
    client.close()
