"""ftp.py

Обёртка над ftplib.FTP для:
- безопасного подключения/логина;
- чтения каталога (MLSD) с ретраями на временных сбоях;
- скачивания файлов с поддержкой докачки (REST) и проверкой размера;
- (опционально) чтения хэша через нестандартную команду XMD5.

Ключевая идея: все сетевые/FTP-команды выполняются через _ftp_call(),
который классифицирует ошибки и выполняет повторные попытки при временных сбоях.
"""

from ftplib import FTP, error_perm, error_reply, error_temp, error_proto
from socket import timeout
from time import sleep
from typing import TypedDict, Type, TypeVar, Callable, cast
from pathlib import Path

from loguru import logger

from SRC.SYNC_APP.APP.dto import (
    FTPInput,
    FTPDirItem,
    ConnectError,
    FTPListError,
    DownloadFileError,
    DownloadDirFtpInput,
    ModeSnapShop,
)


class MLSDFacts(TypedDict, total=False):
    """Типизированное описание facts, возвращаемых MLSD/MLST.

    В ftplib mlsd() возвращает пары (name, facts), где facts — dict[str, str].
    Здесь описаны наиболее используемые поля; набор зависит от FTP-сервера.
    """

    type: str
    size: str
    modify: str
    create: str


class ResumingFileDownloadError(Exception):
    """Ошибка при попытке докачки (REST) или при использовании механизма resume.

    Используется как отдельный тип исключения, чтобы различать:
      - первичную загрузку (DownloadFileError);
      - повторную попытку с докачкой (ResumingFileDownloadError).

    Это позволяет вызывающему коду выбирать стратегию: перезапуск с нуля,
    переход в режим докачки или немедленный фейл.
    """

    pass


T = TypeVar("T")
E = TypeVar("E", bound=Exception)


class Ftp:
    """Клиент FTP с ретраями и более строгой обработкой ошибок.

    Атрибуты:
        ftp_input: DTO с настройками подключения/повторов/таймаутов.
        ftp: экземпляр ftplib.FTP (пересоздаётся при _reconnect()).

    Примечание:
        Метод _ftp_call() — центральная точка обработки временных и постоянных ошибок.
    """

    def __init__(self, ftp_input: FTPInput) -> None:
        """Сохраняет входные настройки и создаёт пустой FTP-клиент."""
        self.ftp_input = ftp_input
        self.ftp = FTP()

    # -------------------------
    # --- _ftp_call()
    # -------------------------
    def _is_temporary_ftp_error(self, e: BaseException) -> bool:
        """True для ошибок, при которых имеет смысл повторить попытку."""
        return isinstance(e, (timeout, OSError, error_temp))

    def _raise_permanent_ftp_error(
        self, what: str, err_cls: type[E], e: BaseException
    ) -> None:
        """Переводит протокольные/постоянные ошибки в доменное исключение."""
        if isinstance(e, error_perm):
            raise err_cls(f"Ошибка доступа при {what}:\n{e}") from e
        if isinstance(e, (error_reply, error_proto)):
            raise err_cls(
                f"Протокольная или некорректная ошибка при {what}:\n{e}"
            ) from e

    def _handle_temporary_ftp_error(self, temp_log: str, e: BaseException) -> None:
        """Логирует временную ошибку и пытается переподключиться."""
        logger.warning(f"{temp_log}:\n{e}. Повтор...")

        try:
            self._reconnect()
        except Exception as recon_e:
            logger.info(f"Ошибка переподключения: {recon_e}")

    def _sleep_retry_delay(self) -> None:
        """Пауза между попытками (фиксированный backoff)."""
        delay = self.ftp_input.context.app.ftp_retry_delay_seconds
        sleep(delay)

    def _ftp_call(
        self,
        action: Callable[[], T],
        *,
        what: str,
        err_cls: Type[E],
        temp_log: str,
    ) -> T:
        """Единая обёртка для FTP-вызовов: ретраи + классификация ошибок.

        Делает несколько попыток выполнить `action()`. Временные сетевые/серверные сбои
        (timeout, OSError, error_temp) считаются ретраебельными: пишется warning,
        выполняется попытка переподключения и делается пауза перед следующей попыткой.

        Постоянные/протокольные ошибки (error_perm, error_reply, error_proto) не ретраятся
        и сразу переводятся в доменное исключение `err_cls`.

        Args:
            action: Функция без аргументов, выполняющая один FTP-вызов (одну операцию).
                Должна вернуть результат типа `T` или выбросить исключение ftplib/сети.
            what: Человекочитаемое описание операции (используется в текстах ошибок),
                например: "cwd в /incoming", "MLSD /incoming", "RETR file.bin".
            err_cls: Класс доменного исключения, которое будет выброшено при фатальной
                ошибке или после исчерпания повторов (например, `FTPListError`,
                `DownloadFileError`, `ConnectError`).
            temp_log: Префикс/контекст для логов при временной ошибке (warning),
                например: "Временный сбой при MLSD", "Timeout при RETR".

        Returns:
            Результат выполнения `action()` (тип `T`).

        Raises:
            err_cls: Если произошла постоянная/протокольная ошибка, либо если
                ретраи исчерпаны, либо если произошла неизвестная ошибка.
        """
        repeat = self.ftp_input.context.app.ftp_repeat

        for _ in range(repeat):
            try:
                return action()

            except Exception as e:
                if self._is_temporary_ftp_error(e):
                    self._handle_temporary_ftp_error(temp_log, e)
                    self._sleep_retry_delay()
                    continue

                # постоянные/протокольные — без повторов
                self._raise_permanent_ftp_error(what, err_cls, e)

                # сюда попадём только если e не из известных классов
                raise err_cls(f"Неизвестная ошибка при {what}:\n{e}") from e

        raise err_cls(f"Не удалось выполнить {what} после повторов")

    # ---------------------------
    # connect
    # ---------------------------

    def _safe_connect(self, host: str, time_out: int) -> None:
        """Подключение к FTP через _ftp_call() (с ретраями на временных сбоях)."""
        self._ftp_call(
            lambda: self.ftp.connect(host, timeout=time_out),
            what=f"подключении к FTP серверу {host!r}",
            err_cls=ConnectError,
            temp_log=f"Не удалось подключиться к {host!r}",
        )

    def _safe_login(self, username: str) -> None:
        """Логин на FTP с развёрнутой классификацией ошибок (530 и т.п.)."""
        try:
            self.ftp.login(user=username, passwd="")
            return

        except error_perm as e:
            if str(e).startswith("530"):
                raise ConnectError(
                    f"Неверные учётные данные при входе на FTP сервер: {username=} passwd="
                    f"\n{e}"
                ) from e
            else:
                raise ConnectError(
                    f"Постоянная ошибка при входе на FTP сервер: {username=} passwd="
                    f"\n{e}"
                ) from e

        except error_temp as e:
            raise ConnectError(
                f"Временная ошибка при входе на FTP сервер. Повторите попытку позже\n{e}"
            ) from e

        except (error_reply, error_proto) as e:
            raise ConnectError(
                f"Неожиданный/некорректный ответ FTP сервера\n{e}"
            ) from e

        except timeout as e:
            raise ConnectError(f"Timeout при входе на FTP сервер\n{e}") from e

        except OSError as e:
            raise ConnectError(f"Сетевая ошибка при входе на FTP сервер:\n{e}") from e

    def connect(self) -> None:
        """Подключается к FTP и выполняет логин"""
        host = self.ftp_input.context.app.ftp_host
        time_out = self.ftp_input.context.app.ftp_timeout_sec
        username = self.ftp_input.context.app.ftp_username

        self._safe_connect(host, time_out)
        self._safe_login(username)

    # ---------------------------
    # Download dir
    # ---------------------------
    def _safe_cwd_ftp(self, path: str) -> None:
        """Переход на директорию с ретраями"""
        self._ftp_call(
            lambda: self.ftp.cwd(path),
            what=f"переходе к директории {path!r}",
            err_cls=FTPListError,
            temp_log=f"Сбой/таймаут при чтении директории {path!r}",
        )

    def _safe_mlsd(self) -> list[tuple[str, MLSDFacts]]:
        """MLSD с ретраями."""
        return self._ftp_call(
            lambda: cast(list[tuple[str, MLSDFacts]], list(self.ftp.mlsd())),
            what="MLSD",
            err_cls=FTPListError,
            temp_log="Сбой/таймаут при чтении MLSD. Проверьте есть ли MLSD на FTP сервере.",
        )

    def _dir_item_from_mlsd(
        self, ftp_root: str, name: str, facts: MLSDFacts, data: DownloadDirFtpInput
    ) -> FTPDirItem | None:
        """построить элемент снапшота из записи MLSD"""
        # Полный путь до файла на FTP (унифицируем слеши).
        remote_full = f"{ftp_root.rstrip('/')}/{name}" if ftp_root else name

        try:
            # Размер берём из MLSD facts (если сервер его даёт).
            size = self._get_size(facts=facts)
            # Хэш запрашиваем отдельной командой (XMD5), если включён соответствующий режим.
            md5_hash = self._get_hmd5(remote_full, data)
            return FTPDirItem(remote_full=remote_full, size=size, md5_hash=md5_hash)
        except DownloadFileError as e:
            # Ошибка на отдельном файле не валит весь список: логируем и пропускаем.
            logger.info(f"Пропускаю файл {remote_full!r}: {e}")
            return None

    def _build_dir_items(
        self,
        raw_items: list[tuple[str, MLSDFacts]],
        ftp_root: str,
        data: DownloadDirFtpInput,
    ) -> list[FTPDirItem]:
        items: list[FTPDirItem] = []
        for name, facts in raw_items:
            if (data.only_for is not None and name not in data.only_for) or facts.get(
                "type"
            ) != "file":
                continue  # директории/ссылки/прочее игнорируем

            item = self._dir_item_from_mlsd(ftp_root, name, facts, data)
            if item is not None:
                items.append(item)

        return items

    def download_dir(self, data: DownloadDirFtpInput) -> list[FTPDirItem]:
        """Считывает каталог FTP и возвращает список файлов.

        Использует MLSD; при необходимости дополнительно запрашивает XMD5 для выбранных файлов.
        Ошибки чтения отдельного файла не прерывают обработку списка.
        """

        # 1) Переходим в корневую директорию через безопасный вызов с ретраями
        ftp_root = self.ftp_input.context.app.ftp_root
        self._safe_cwd_ftp(ftp_root)

        # 2) Считываем содержимое директории через MLSD (возвращает name + facts)
        raw_items = self._safe_mlsd()

        # 3) формирование списка элементов директории
        return self._build_dir_items(raw_items, ftp_root, data)

    # ---------------------------
    # Download with resume
    # ---------------------------
    def _calc_offset(self, local_path: str, expected_size: int) -> int:
        """Определяет смещение для докачки (REST) на основе локального файла.

        Если resume=False или файла нет — начинаем с нуля.
        Если локальный файл больше ожидаемого — докачка бессмысленна, начинаем заново.
        """
        path = Path(local_path)
        if not path.exists():
            return 0

        offset = path.stat().st_size
        return 0 if offset > expected_size else offset

    @staticmethod
    def _quote_remote(path: str) -> str:
        """
        Минимальная “кавычка” для FTP-команд, чтобы пережить пробелы в именах.
        Большинство серверов принимает двойные кавычки.
        """
        # Экранирование двойных кавычек внутри имени на случай экзотики.
        safe = path.replace('"', r"\"")
        return f'"{safe}"'

    def _download_attempt(
        self,
        remote_full_name: str,
        local_full_name: str,
        *,
        offset: int,
        blocksize: int,
    ) -> None:
        """Выполняет одну попытку скачивания файла (с учётом offset для докачки)."""
        # Создаём директории под локальный файл, если их нет.
        local_path = Path(local_full_name)

        self.make_safe_dir_name(local_path)
        # При докачке пишем в конец (append binary), иначе перезаписываем (write binary).
        mode = "ab" if offset else "wb"
        with open(local_path, mode) as f:
            # retrbinary пишет данные блоками; callback = f.write.
            self._ftp_call(
                lambda: self.ftp.retrbinary(
                    f"RETR {self._quote_remote(remote_full_name)}",
                    f.write,
                    blocksize=blocksize,
                    rest=offset if offset else None,
                ),
                what=f"загрузка файла {remote_full_name!r}",
                err_cls=DownloadFileError if offset == 0 else ResumingFileDownloadError,
                temp_log=f"Сбой/таймаут при загрузке файла {remote_full_name!r}",
            )

    def _local_size(self, full_name: str) -> int:
        """Возвращает размер локального файла или -1, если файла нет."""
        path = Path(full_name)
        return path.stat().st_size if path.exists() else -1

    def make_safe_dir_name(self, file: str | Path) -> Path:
        """Гарантирует существование родительской директории для file и возвращает её Path."""
        parent = Path(file).resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
        return parent

    def _download_file_with_resume(
        self, remote_item: FTPDirItem, local_path: str, *, blocksize: int
    ) -> None:
        """Скачиваем файл с возможной докачкой"""
        try:
            self._download_attempt(
                remote_full_name=remote_item.remote_full,
                local_full_name=local_path,
                offset=0,
                blocksize=blocksize,
            )

        except DownloadFileError as e:
            logger.info(
                f"Неудача при загрузке файла {e}.\nОрганизуем догрузку: {remote_item.remote_full!r}"
            )

            if remote_item.size is None:
                raise DownloadFileError(
                    "Догрузка невозможно. FTP сервер не указал размер файла"
                )
            offset = self._calc_offset(local_path, remote_item.size)
            self._download_attempt(
                remote_full_name=remote_item.remote_full,
                local_full_name=local_path,
                offset=offset,
                blocksize=blocksize,
            )

        except ResumingFileDownloadError as e:
            # Постоянная ошибка.
            raise DownloadFileError(
                f"Ошибка при загрузке файла {remote_item.remote_full}:\n{e}"
            )

    def download_file(
        self,
        remote_item: FTPDirItem,
        local_path: str,
        *,
        blocksize: int,
    ) -> None:
        """Скачивает один файл и проверяет итоговый размер."""

        # 1) Скачиваем файл
        self._download_file_with_resume(remote_item, local_path, blocksize=blocksize)

        # 2) если размер совпал — готово
        local_size = self._local_size(local_path)
        if remote_item.size is None:
            raise DownloadFileError(
                f"FTP сервер не указал размер файла {remote_item.remote_full}\n"
                f"Контроль по размеру проводится не будет."
            )
        if local_size == remote_item.size:
            return

        # 3) иначе — фиксируем неудачу
        raise DownloadFileError(
            f"Размер не совпал после скачивания.\n"
            f"remote={remote_item.remote_full}\n"
            f"ожидаемый размер expected={remote_item.size}, реальный размер local={local_size}"
        )

    def _get_size(
        self,
        facts: MLSDFacts,
    ) -> int | None:
        """Извлекает размер файла из MLSD facts (поле "size")."""
        size: int | None = None
        if "size" in facts:
            try:
                size = int(facts["size"])
            except ValueError:
                size = None

        return size

    def _get_hmd5(self, full_remote: str, inp: DownloadDirFtpInput) -> str | None:
        """Возвращает MD5 (XMD5) для файла или None, если режим md5 выключен."""
        if inp.with_md5 == ModeSnapShop.LITE_MODE:
            return None

        responses = self._ftp_call(
            lambda: self.ftp.sendcmd("XMD5 " + self._quote_remote(full_remote)),
            what=f"XMD5 для {full_remote!r}",
            err_cls=DownloadFileError,
            temp_log=f"Сбой/таймаут при чтении XMD5 для файла {full_remote!r}",
        )
        parts = responses.split()
        md5_hash = parts[-1] if parts else None
        if md5_hash is None:
            raise DownloadFileError(
                f"Пустой/некорректный ответ XMD5 для {full_remote}: {responses!r}"
            )
        return md5_hash

    def _reconnect(self) -> None:
        """Пересоздаёт FTP-сессию и пытается восстановить рабочее состояние (connect/login/cwd).

        Важно: здесь намеренно "одна попытка" без _ftp_call() -> ретраи делаются снаружи.
        """
        try:
            try:
                self.ftp.close()
            except Exception:
                pass

            self.ftp = FTP()

            host = self.ftp_input.context.app.ftp_host
            time_out = self.ftp_input.context.app.ftp_timeout_sec
            username = self.ftp_input.context.app.ftp_username
            root = self.ftp_input.context.app.ftp_root

            # ОДНА попытка. Без _ftp_call и без ретраев.
            self.ftp.connect(host, timeout=time_out)
            self.ftp.login(user=username, passwd="")

            if root:
                self.ftp.cwd(root)

        except (timeout, OSError, error_temp, error_perm) as e:
            # логируем и ПЕРЕБРАСЫВАЕМ
            logger.error(f"Не удалось переподключиться к FTP:\n{e}")
            raise
