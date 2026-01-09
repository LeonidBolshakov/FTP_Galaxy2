"""ftp.py

Обёртка над ftplib.FTP для:
- безопасного подключения/логина;
- чтения каталога (MLSD) с ретраями на временных сбоях;
- скачивания файлов с поддержкой докачки (REST) и проверкой размера;
- (опционально) чтения хэша через нестандартную команду XMD5.

Ключевая идея: все сетевые/FTP-команды выполняются через _ftp_call(),
который классифицирует ошибки и выполняет повторные попытки при временных сбоях.
"""

import posixpath
import os
from ftplib import FTP, error_perm, error_reply, error_temp, error_proto
from socket import timeout
from time import sleep, monotonic
from typing import TypedDict, Type, TypeVar, Callable, cast, BinaryIO, NoReturn, Literal
from pathlib import Path
from dataclasses import dataclass

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

TEMP_EXCEPTIONS = (
    timeout,
    OSError,
    error_temp,
    EOFError,
    ConnectionResetError,
    BrokenPipeError,
    AttributeError,  # sock is None -> not connected
)  # Исключения, при которых имеет смысл повторить попытку обращения к FTP


class MLSDFacts(TypedDict, total=False):
    """Типизированное описание facts, возвращаемых MLSD/MLST.

    В ftplib mlsd() возвращает пары (path, facts), где facts — dict[str, str].
    Здесь описаны наиболее используемые поля; набор зависит от FTP-сервера.
    """

    type: str
    size: str
    modify: str
    create: str


@dataclass
class _RetrWriterWithProgress:
    f: BinaryIO
    label: str
    downloaded: int
    update_every_sec: float = 0.5

    _last_ts: float = 0.0

    def __call__(self, chunk: bytes) -> None:
        self.f.write(chunk)
        self.downloaded += len(chunk)

        now = monotonic()
        if now - self._last_ts >= self.update_every_sec:
            print(f"\r{self.label!r}: {self.downloaded} байт", end="", flush=True)
            self._last_ts = now

    def finish(self) -> None:
        print(f"\r<-- {self.label!r}: {self.downloaded} байт", flush=True)


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
        """Сохраняет входные настройки"""
        self.ftp_input = ftp_input
        self.ftp = ftp_input.ftp
        self.blocksize = ftp_input.context.app.ftp_blocksize

    # -------------------------
    # --- _ftp_call()
    # -------------------------
    def _is_temporary_ftp_error(self, e: BaseException) -> bool:
        """True для ошибок, при которых имеет смысл повторить попытку."""
        return isinstance(e, TEMP_EXCEPTIONS)

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

    def _handle_temporary_ftp_error(
            self, temp_log: str, e: BaseException
    ) -> Exception | None:
        """Логирует временную ошибку и пытается переподключиться.

        Returns:
            Исключение переподключения (если переподключиться не удалось), иначе None.
        """

        logger.info("{}:\n{}. Повтор...", temp_log, e)

        try:
            self._reconnect()
        except Exception as recon_e:
            # Важно: не прерываем ретраи _ftp_call(), но сохраняем причину
            logger.info("Ошибка переподключения: {}", recon_e)
            return recon_e

        return None

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
        (timeout, OSError, error_temp) считаются повторяемыми: пишется warning,
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
            temp_log: Префикс/контекст для логов при временной ошибке (info),
                например: "Временный сбой при MLSD", "Timeout при RETR".

        Returns:
            Результат выполнения `action()` (тип `T`).

        Raises:
            err_cls: Если произошла постоянная/протокольная ошибка, либо если
                ретраи исчерпаны, либо если произошла неизвестная ошибка.
        """
        repeat = self.ftp_input.context.app.ftp_repeat
        last_error: BaseException | None = None

        for _ in range(repeat):
            try:
                return action()

            except Exception as e:
                if self._is_temporary_ftp_error(e):
                    recon_e = self._handle_temporary_ftp_error(temp_log, e)
                    last_error = recon_e or e
                    self._sleep_retry_delay()
                    continue

                # постоянные/протокольные — без повторов
                self._raise_permanent_ftp_error(what, err_cls, e)

                # сюда попадём только если e не из известных классов
                raise err_cls(f"Неизвестная ошибка при {what}- {e}") from e
        raise err_cls(
            f"Не удалось выполнить {what} после {repeat} попыток.\n"
            f"Последняя ошибка: {last_error}"
        ) from last_error

    # ---------------------------
    # connect
    # ---------------------------

    def _safe_connect(self, host: str, time_out: float) -> None:
        """Подключение к FTP через _ftp_call() (с ретраями на временных сбоях)."""
        self._ftp_call(
            lambda: self.ftp.connect(host, timeout=time_out),
            what=f"подключен. к FTP серверу {host!r}",
            err_cls=ConnectError,
            temp_log=f"Не удалось подключиться к {host!r}",
        )

    def _safe_login(self, username: str) -> None:
        """Логин на FTP с развёрнутой классификацией ошибок (530 и т.п.)."""

        def _raise_fail(msg: str, exc: BaseException) -> NoReturn:
            raise ConnectionError(f"{msg}\n{exc}") from exc

        try:
            self.ftp.login(user=username, passwd="")
            return

        except error_perm as e:
            if str(e).startswith("530"):
                _raise_fail(
                    f"Неверные учётные данные при входе на FTP сервер: {username=} passwd=***",
                    e,
                )
            _raise_fail(
                f"Постоянная ошибка при входе на FTP сервер: {username=} passwd=***",
                e,
            )

        except error_temp as e:
            _raise_fail(
                "Временная ошибка при входе на FTP сервер. Повторите попытку позже", e
            )

        except (error_reply, error_proto) as e:
            _raise_fail("Неожиданный/некорректный ответ FTP сервера", e)

        except timeout as e:
            _raise_fail("Timeout при входе на FTP сервер", e)

        except OSError as e:
            _raise_fail("Сетевая ошибка при входе на FTP сервер", e)

    def connect(self) -> None:
        """Подключается к FTP и выполняет логин"""
        host = self.ftp_input.context.app.ftp_host
        time_out = self.ftp_input.context.app.ftp_timeout_sec
        username = self.ftp_input.context.app.ftp_username

        self._safe_connect(host, time_out)
        self._safe_login(username)

    # ---------------------------
    # Download dir_path
    # ---------------------------
    def _safe_cwd_ftp(self, path: str) -> None:
        """Переход на директорию с ретраями"""
        self._ftp_call(
            lambda: self.ftp.cwd(path),
            what=f"перех. к директории {path!r}",
            err_cls=FTPListError,
            temp_log=f"Сбой/таймаут при чтении директории {path!r}",
        )

    def _safe_mlsd(self) -> list[tuple[str, MLSDFacts]]:
        """MLSD с ретраями."""
        return self._ftp_call(
            lambda: cast(list[tuple[str, MLSDFacts]], list(self.ftp.mlsd())),
            what="чтен. MLSD",
            err_cls=FTPListError,
            temp_log="Сбой/таймаут при чтении MLSD. Проверьте есть ли MLSD на FTP сервере.",
        )

    def _dir_item_from_mlsd(
        self, ftp_root: str, name: str, facts: MLSDFacts, data: DownloadDirFtpInput
    ) -> FTPDirItem:
        """построить элемент снапшота из записи MLSD"""

        # Размер берём из MLSD facts (если сервер его даёт).

        remote_full = posixpath.join(ftp_root, name)
        md5_hash = self._get_hmd5(remote_full, data)
        size = self._get_size(facts=facts)

        return FTPDirItem(remote_full=remote_full, size=size, md5_hash=md5_hash)

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
            items.append(item)

        return items

    def download_dir(self, data: DownloadDirFtpInput) -> list[FTPDirItem]:
        """Считывает каталог FTP и возвращает список FTPDirItem.

        Использует MLSD; при необходимости, дополнительно запрашивает XMD5 для выбранных файлов.
        """

        # 1) Переходим в корневую директорию через безопасный вызов с ретраями
        ftp_root = self.ftp_input.context.app.ftp_root
        self._safe_cwd_ftp(ftp_root)

        # 2) Считываем содержимое директории через MLSD (возвращает path + facts)
        raw_items = self._safe_mlsd()

        # 3) Формируем список элементов директории
        return self._build_dir_items(raw_items, ftp_root, data)

    # ---------------------------
    # Download with resume
    # ---------------------------
    def _calc_offset(self, local_path: Path, expected_size: int) -> int:
        """Определяет смещение для докачки (REST) на основе локального файла.

        Если resume=False или файла нет — начинаем с нуля.
        Если локальный файл больше ожидаемого — докачка бессмысленна, начинаем заново.
        """
        if not local_path.exists():
            return 0

        offset = local_path.stat().st_size
        return 0 if offset > expected_size else offset

    def _retrbinary_with_resume(
            self,
            remote_full_name: str,
            f: BinaryIO,
            callback,  # Callable[[bytes], None]
    ) -> str:
        # ВАЖНО: вызывается на каждый ретрай -> rest пересчитывается каждый раз
        f.flush()
        f.seek(0, os.SEEK_END)  # на всякий случай в конец
        rest = f.tell()

        return self.ftp.retrbinary(
            f"RETR {remote_full_name}",
            callback,
            rest=rest or None,  # 0 -> None
            blocksize=self.blocksize,
        )

    def _download_attempt(
        self,
        remote_full_name: str,
            local_full_name: Path,
        *,
        offset: int,
    ) -> None:
        """Скачивание файла с учётом offset (REST) и ретраями внутри _ftp_call()."""

        self.make_safe_dir_name(local_full_name)

        mode: Literal["ab", "wb"] = "ab" if offset else "wb"

        with open(local_full_name, mode) as f:
            writer = _RetrWriterWithProgress(
                f=f, label=remote_full_name, downloaded=offset
            )

            try:
                self._ftp_call(
                    lambda: self._retrbinary_with_resume(remote_full_name, f, writer),
                    what=f"загруз. файла {remote_full_name!r}",
                    err_cls=DownloadFileError,
                    temp_log=f"Сбой/таймаут при загрузке файла {remote_full_name!r}",
                )
            finally:
                writer.finish()

    def _local_size(self, path: Path) -> int:
        """Возвращает размер локального файла или 0, если файла нет."""
        return path.stat().st_size if path.exists() else 0

    def make_safe_dir_name(self, file: str | Path) -> Path:
        """Гарантирует существование родительской директории для file и возвращает её Path."""
        parent = Path(file).resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
        return parent

    def _download_attempt_as_download_error(
            self,
            *,
            remote_full_name: str,
            local_full_name: Path,
            offset: int,
    ) -> None:
        """Скачивает/докачивает файл и поднимает DownloadFileError при любой ошибке докачки."""
        try:
            self._download_attempt(
                remote_full_name=remote_full_name,
                local_full_name=local_full_name,
                offset=offset,
            )
        except DownloadFileError as e:
            raise DownloadFileError(
                f"Ошибка при загрузке файла {remote_full_name!r}:\n{e}"
            ) from e

    def _try_resume_after_failure(
            self,
            *,
            remote_item: FTPDirItem,
            local_path: Path,
            cause: Exception,
    ) -> None:
        """Если возможно, пытается докачать файл после неудачной загрузки.

        Выбрасывает:
          - DownloadFileError: если докачка невозможна или докачка тоже не удалась.
          - пробрасывает исходное исключение, если докачка не имеет смысла (offset<=0).
        """
        if remote_item.size is None:
            raise DownloadFileError(
                "Догрузка невозможна: FTP сервер не указал размер файла."
            ) from cause

        offset = self._calc_offset(local_path, remote_item.size)
        if offset <= 0:
            # Нечего докачивать: повторная попытка будет идентична первой.
            raise  # проброс исходного исключения (из except-блока, где вызван этот метод)

        logger.info(
            "Неудача при загрузке, пробуем докачку: {!r} (offset={})",
            remote_item.remote_full,
            offset,
        )

        self._download_attempt_as_download_error(
            remote_full_name=remote_item.remote_full,
            local_full_name=local_path,
            offset=offset,
        )

    def _download_file_with_resume(
            self, remote_item: FTPDirItem, local_path: Path, offset: int = 0
    ) -> None:
        """Скачиваем файл с возможной докачкой"""
        # 1) пробуем скачать с нуля
        try:
            self._download_attempt(
                remote_full_name=remote_item.remote_full,
                local_full_name=local_path,
                offset=offset,
            )

        except DownloadFileError as e:
            self._try_resume_after_failure(
                remote_item=remote_item,
                local_path=local_path,
                cause=e,
            )

    def download_file(
            self, remote_full_item: FTPDirItem, local_full_path: Path, local_file_size: int
    ) -> None:
        """Скачивает один файл и проверяет итоговый размер."""

        # 1) Скачиваем файл
        self._download_file_with_resume(
            remote_full_item, local_full_path, local_file_size
        )

        # 2) если размер совпал — готово
        local_size = self._local_size(local_full_path)
        if remote_full_item.size is None:
            raise DownloadFileError(
                f"FTP сервер не указал размер файла {remote_full_item.remote_full}\n"
                f"Контроль по размеру проводится не будет."
            )
        if local_size == remote_full_item.size:
            return

        # 3) иначе — фиксируем неудачу
        raise DownloadFileError(
            f"Размер не совпал после скачивания.\n"
            f"remote={remote_full_item.remote_full}\n"
            f"ожидаемый размер expected={remote_full_item.size}, реальный размер local={local_size}"
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
            lambda: self.ftp.sendcmd(f"XMD5 {full_remote}"),
            what=f"чтен. XMD5 для {full_remote!r}",
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
            self.ftp.connect(host=host, timeout=time_out)
            self.ftp.login(user=username, passwd="")

            if root:
                self.ftp.cwd(root)

        except (timeout, OSError, error_temp, error_perm) as e:
            # логируем и ПЕРЕБРАСЫВАЕМ
            self.ftp.close()
            logger.error("Не удалось переподключиться к FTP:\n{}", e)
            raise
