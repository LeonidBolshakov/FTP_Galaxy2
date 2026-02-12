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
from ftplib import FTP, error_perm, error_reply, error_temp, error_proto, all_errors
from socket import timeout
from time import sleep, monotonic
from typing import TypedDict, Type, TypeVar, Callable, cast, BinaryIO, Literal
from pathlib import Path
from dataclasses import dataclass

from loguru import logger

from SYNC_APP.INFRA.utils import fs_call

from SYNC_APP.APP.dto import (
    FTPInput,
    FileSnapshot,
    DownloadDirFtpInput,
    ModeSnapshot,
    RepositorySnapshot,
)

from GENERAL.errors import ConnectError, DownloadDirError, DownloadFileError

TEMP_EXCEPTIONS = (
    timeout,
    OSError,
    error_temp,
    EOFError,
    ConnectionResetError,
    BrokenPipeError,
    AttributeError,  # sock is None вызывает AttributeError
)  # Исключения, при которых имеет смысл повторить попытку обращения к FTP


class MLSDFacts(TypedDict, total=False):
    """Типизированное описание facts, возвращаемых MLSD/MLST.

    В `ftplib.FTP.mlsd()` возвращает пары ``(name, facts)``, где ``facts`` — это
    ``dict[str, str]`` с метаданными, предоставленными сервером. Ниже описаны
    наиболее используемые поля; фактический набор ключей зависит от реализации FTP.
    """

    # fmt: off
    type                        : str
    size                        : str
    modify                      : str
    create                      : str


@dataclass
class _RetrWriterWithProgress:
    """Callable-обёртка для записи чанков `retrbinary()` с выводом прогресса.

    Используется как callback для `FTP.retrbinary()`: пишет полученные байты в файл,
    увеличивает счётчик скачанного и периодически печатает прогресс в stdout.

    Атрибуты dataclass:
        f: Открытый бинарный файл для записи.
        label: Метка (обычно имя файла) для печати прогресса.
        downloaded: Сколько байт уже скачано (важно для докачки).
        update_every_sec: Минимальный интервал обновления прогресса.
    """

    f: BinaryIO
    label: str
    downloaded: int
    update_every_sec: float = 0.5
    _last_ts: float = 0.0
    # fmt: on

    def __call__(self, chunk: bytes) -> None:
        """Записывает chunk в файл и (периодически) печатает прогресс скачивания."""
        self.f.write(chunk)
        self.downloaded += len(chunk)

        now = monotonic()
        if now - self._last_ts >= self.update_every_sec:
            print(f"\r* {self.label!r}: {self.downloaded} байт", end="", flush=True)
            self._last_ts = now

    def finish(self) -> None:
        """Печатает финальное сообщение о количестве скачанных байт."""
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

        Parameters
        ----------
        temp_log : str
            Контекстное сообщение для логов.
        e : BaseException
            Исходная ошибка временного сбоя.

        Returns
        -------
        Exception | None
            Ошибка переподключения (если переподключение не удалось), иначе ``None``.
        """

        logger.info("{}:\n{}. Повтор...", temp_log, e)

        try:
            self._reconnect()
        except Exception as recon_e:
            # Важно: не прерываем ретраи _ftp_call(), но сохраняем причину
            logger.warning("Ошибка переподключения: {}", recon_e)
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
        """Единая обёртка для FTP-вызовов: ретраи и классификация ошибок.

        Делает несколько попыток выполнить `action()`. Временные сетевые/серверные сбои
        (timeout, OSError, error_temp, ...) считаются повторяемыми: пишется лог,
        выполняется попытка переподключения и делается пауза перед следующей попыткой.

        Постоянные/протокольные ошибки (error_perm, error_reply, error_proto) не
        повторяются и сразу переводятся в доменное исключение `err_cls`.

        Parameters
        ----------
        action : Callable[[], T]
            Функция без аргументов, выполняющая одну FTP-операцию и возвращающая `T`.
        what : str
            Человекочитаемое описание операции (для сообщений об ошибках), например:
            ``"cwd в /incoming"``, ``"MLSD /incoming"``, ``"RETR file.bin"``.
        err_cls : type[E]
            Класс доменного исключения, которое поднимается при фатальной ошибке или
            после исчерпания повторов.
        temp_log : str
            Контекст/префикс для логов при временной ошибке.

        Returns
        -------
        T
            Результат выполнения `action()`.

        Raises
        ------
        err_cls
            При постоянной/протокольной ошибке, при исчерпании повторов или при
            неизвестной ошибке.
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
                raise err_cls(f"Неизвестная ошибка при {what}\n{repr(e)}") from e
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
            what=f"подключении к FTP серверу {host!r}",
            err_cls=ConnectError,
            temp_log=f"Не удалось подключиться к {host!r}",
        )

    def _safe_login(self, username: str) -> None:
        """Логин на FTP через _ftp_call() (с ретраями на временных сбоях).
        530 считаем фатальной ошибкой (не ретраим), но оставляем понятное сообщение.
        """

        def action() -> None:
            try:
                # anonymous, пароль пустой
                self.ftp.login(user=username, passwd="")
                return None

            except error_perm as e:
                # 530 — неверные учётные данные / вход запрещён
                if str(e).startswith("530"):
                    # Делаем это "постоянной" ошибкой, чтобы _ftp_call НЕ ретраил,
                    # но при этом в сообщении было понятно, что случилось.
                    raise error_perm(
                        f"530 Неверные учётные данные или вход запрещён: user={username!r} passwd=<empty>. "
                        f"Ответ сервера: {e}"
                    ) from e
                # Любая другая error_perm тоже не должна ретраиться
                raise

        # Временные ошибки (timeout/OSError/error_temp/EOFError/...) ретраятся внутри _ftp_call()
        self._ftp_call(
            action,
            what=f"входе на FTP (login) как {username!r}",
            err_cls=ConnectError,
            temp_log=f"Сбой/таймаут при логине на FTP как {username!r}",
        )

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
            what=f"переход к директории {path!r}",
            err_cls=DownloadDirError,
            temp_log=f"Сбой/таймаут при чтении директории {path!r}",
        )

    def _safe_mlsd(self) -> list[tuple[str, MLSDFacts]]:
        """MLSD с ретраями."""
        return self._ftp_call(
            lambda: cast(list[tuple[str, MLSDFacts]], self.ftp.mlsd()),
            what="чтение MLSD",
            err_cls=DownloadDirError,
            temp_log="Сбой/таймаут при чтении MLSD. Проверьте есть ли MLSD на FTP сервере.",
        )

    def _build_dir_items(
        self,
        raw_items: list[tuple[str, MLSDFacts]],
        ftp_root: str,
        data: DownloadDirFtpInput,
    ) -> RepositorySnapshot:
        """Преобразует результат MLSD в `RepositorySnapshot`.

        Фильтрует только файлы (``facts["type"] == "file"``), учитывает ограничение
        `only_for` и, при необходимости, запрашивает хэш (XMD5).

        Parameters
        ----------
        raw_items : list[tuple[str, MLSDFacts]]
            Элементы, возвращённые MLSD.
        ftp_root : str
            Путь каталога на FTP, относительно которого строится полный путь к файлу.
        data : DownloadDirFtpInput
            Параметры построения снимка (фильтрация и режим хэша).

        Returns
        -------
        RepositorySnapshot
            Снимок файлов каталога.
        """
        items = RepositorySnapshot(files={})

        try:
            for name, facts in raw_items:
                if facts.get("type") != "file":
                    continue

                if data.only_for is not None and name not in data.only_for:
                    continue

                size = self._get_size(facts)
                remote_full_name = posixpath.join(ftp_root, name)
                md5_hash = self._get_hmd5(remote_full_name, data.hash_mode)
                items.files[name] = FileSnapshot(
                    name=name, size=size, md5_hash=md5_hash
                )
        except all_errors as e:
            raise ConnectError(f"ошибка при чтении элементов каталога\n{e}") from e

        return items

    def download_dir(self, data: DownloadDirFtpInput) -> RepositorySnapshot:
        """Считывает корневой каталог FTP и возвращает снимок репозитория.

        Использует MLSD; при необходимости дополнительно запрашивает XMD5 для выбранных
        файлов (если включён соответствующий режим хэширования).
        """

        # 1) Переходим в корневую директорию через безопасный вызов с ретраями
        ftp_root = self.ftp_input.context.app.ftp_root
        self._safe_cwd_ftp(ftp_root)

        # 2) Считываем содержимое директории через MLSD (возвращает name + facts)
        raw_items = self._safe_mlsd()

        # 3) Формируем список элементов директории
        return self._build_dir_items(raw_items, ftp_root, data)

    # ---------------------------
    # Download with resume
    # ---------------------------
    def _calc_offset(self, local_path: Path, expected_size: int) -> int:
        """Определяет смещение для докачки (REST) на основе локального файла.

        Если локального файла нет — начинаем с нуля.
        Если локальный файл больше ожидаемого — докачка бессмысленна, возвращаем 0
        (перезапись с начала).
        """
        if not local_path.exists():
            return 0

        offset = local_path.stat().st_size
        return 0 if offset > expected_size else offset

    def _retrbinary_with_resume(
            self, file_name: str, f: BinaryIO, callback: Callable[[bytes], None]
    ) -> str:
        """Выполняет `RETR` с поддержкой докачки через параметр `rest`.

        Смещение (`rest`) берётся из текущей позиции файлового объекта `f` (размера уже
        записанной части). Это позволяет FTP-серверу продолжить передачу с нужного места.
        """
        # ВАЖНО: вызывается на каждый ретрай -> rest пересчитывается каждый раз
        f.flush()
        f.seek(0, os.SEEK_END)  # на всякий случай в конец
        rest = f.tell()

        return self.ftp.retrbinary(
            f"RETR {file_name}",
            callback,
            rest=rest or None,  # 0 -> None
            blocksize=self.blocksize,
        )

    def _download_attempt(
        self,
            file_name: str,
            local_full_path: Path,
        *,
        offset: int,
    ) -> None:
        """Скачивание файла с учётом offset (REST) и ретраями внутри _ftp_call()."""

        self._make_safe_dir_name(local_full_path)

        mode: Literal["ab", "wb"] = "ab" if offset else "wb"

        with open(local_full_path, mode) as f:
            writer = _RetrWriterWithProgress(f=f, label=file_name, downloaded=offset)

            try:
                self._ftp_call(
                    lambda: self._retrbinary_with_resume(file_name, f, writer),
                    what=f"загрузку файла {file_name!r}",
                    err_cls=DownloadFileError,
                    temp_log=f"Сбой/таймаут при загрузке файла {file_name!r}",
                )
            finally:
                writer.finish()

    def _local_size(self, path: Path) -> int:
        """Возвращает размер локального файла или 0, если файла нет."""
        return path.stat().st_size if path.exists() else 0

    def _make_safe_dir_name(self, file: str | Path) -> Path:
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
                file_name=remote_full_name,
                local_full_path=local_full_name,
                offset=offset,
            )
        except DownloadFileError as e:
            raise DownloadFileError(
                f"Ошибка при загрузке файла {remote_full_name!r}:\n{e}"
            ) from e

    def _try_resume_after_failure(
            self,
            *,
            snapshot: FileSnapshot,
            local_path: Path,
            cause: Exception,
    ) -> None:
        """Пытается выполнить докачку файла после неудачной загрузки.

        Если FTP-сервер сообщает размер файла, вычисляется offset по локальному файлу и
        выполняется повторная попытка с REST.

        Parameters
        ----------
        snapshot : FileSnapshot
            Снимок удалённого файла (имя и ожидаемый размер).
        local_path : Path
            Путь к локальному файлу, который может содержать частично скачанные данные.
        cause : Exception
            Исходная ошибка загрузки.

        Raises
        ------
        DownloadFileError
            Если докачка невозможна (неизвестен размер) или докачка тоже не удалась.
        Exception
            Пробрасывается `cause`, если докачка не имеет смысла (offset <= 0).
        """
        if snapshot.size is None:
            raise DownloadFileError(
                "Догрузка невозможна: FTP сервер не указал размер файла."
            ) from cause

        offset = self._calc_offset(local_path, snapshot.size)
        if offset <= 0:
            # Нечего докачивать: повторная попытка будет идентична первой.
            raise cause  # проброс исходного исключения (из except-блока, где вызван этот метод)

        logger.info(
            "Неудача при загрузке, пробуем докачку: {!r} (offset={})",
            snapshot.name,
            offset,
        )

        self._download_attempt_as_download_error(
            remote_full_name=snapshot.name,
            local_full_name=local_path,
            offset=offset,
        )

    def _download_file_with_resume(
            self, snapshot: FileSnapshot, local_full_path: Path, offset: int = 0
    ) -> None:
        """Скачиваем файл с возможной докачкой"""
        try:
            self._download_attempt(
                file_name=snapshot.name,
                local_full_path=local_full_path,
                offset=offset,
            )

        except DownloadFileError as e:
            self._try_resume_after_failure(
                snapshot=snapshot,
                local_path=local_full_path,
                cause=e,
            )

    def download_file(self, snapshot: FileSnapshot, local_full_path: Path) -> None:
        """Скачивает один файл и проверяет итоговый размер."""
        if snapshot.size is None:
            raise DownloadFileError(
                f"{snapshot.name}\n" f"Размер не указан сервером — файл пропущен."
            )

        offset = self._local_size(local_full_path)
        if offset == snapshot.size:
            return

        if offset > self._safe_size(snapshot.size):
            fs_call(
                local_full_path,
                "удаление",
                lambda: local_full_path.unlink(missing_ok=True),
            )
            offset = 0

        # 1) Скачиваем файл
        self._download_file_with_resume(
            snapshot=snapshot,
            local_full_path=local_full_path,
            offset=offset,
        )

        # 2) если размер совпал — готово
        local_file_size = self._local_size(local_full_path)
        if local_file_size == snapshot.size:
            return

        # 3) иначе — фиксируем неудачу
        raise DownloadFileError(
            f"Размер скаченного файла не совпал с размерос файла на FTP.\n"
            f"Имя файла - {snapshot.name}\n"
            f"Ожидаемый размер expected={snapshot.size}, реальный размер local={local_file_size}"
        )

    def _get_size(
        self,
        facts: MLSDFacts,
    ) -> int | None:
        """Извлекает размер файла из MLSD facts (поле "size")."""
        size: int | None = None
        if "size" not in facts:
            return None

        try:
            size = int(facts["size"])
        except ValueError:
            size = None

        return size

    def _get_hmd5(self, full_remote: str, hash_mode: ModeSnapshot) -> str | None:
        """Возвращает MD5 (XMD5) для файла или None, если режим md5 выключен."""
        if hash_mode == ModeSnapshot.LITE_MODE:
            return None

        responses = self._ftp_call(
            lambda: self.ftp.sendcmd(f"XMD5 {full_remote}"),
            what=f"чтение XMD5 для {full_remote!r}",
            err_cls=DownloadDirError,
            temp_log=f"Сбой/таймаут при чтении XMD5 для файла {full_remote!r}",
        )
        parts = responses.split()
        md5_hash = parts[-1] if parts else None
        if md5_hash is None:
            raise DownloadDirError(
                f"Пустой/некорректный ответ XMD5 для {full_remote}: {responses!r}"
            )
        return md5_hash

    def _reconnect(self) -> None:
        """Пересоздаёт FTP-сессию и пытается восстановить рабочее состояние (connect/login/cwd).

        Важно: здесь намеренно "одна попытка" без _ftp_call().
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

    def close(self) -> None:
        """Корректно завершает FTP-сессию (QUIT) и закрывает соединение при необходимости."""
        try:
            self.ftp.quit()
        except Exception:
            try:
                self.ftp.close()
            except Exception:
                pass

    def _safe_size(self, size: int | None) -> int:
        """Возвращает `size` или 0, если размер неизвестен (None)."""
        return size if size is not None else 0
