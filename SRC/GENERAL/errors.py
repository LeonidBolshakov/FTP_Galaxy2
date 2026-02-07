class AppError(Exception):
    exit_code: int = 1
    log_message: str = "Ошибка приложения"


class ConnectError(AppError):
    log_message: str = "Не удалось подключиться к FTP"


class DownloadFileError(AppError):
    log_message = "Ошибка при чтении файла с FTP"


class DownloadDirError(AppError):
    log_message = "Ошибка при получении списка файлов на FTP"


class ConfigError(AppError):
    log_message = "Ошибка в конфигурации"


class LocalFileAccessError(AppError, OSError):
    log_message = "Ошибка доступа к локальным файлам/каталогам"


class UserAbend(AppError):
    exit_code = 130
    log_message = "Пользователь прекратил работу"


class SkipExecute(AppError):
    exit_code = 777
    """Закончить выаолнение программы"""


class ConfigLoadError(Exception):
    """
    Ошибка загрузки/разбора/валидации конфигурации.

    Используется как единый тип исключения для внешнего слоя приложения.
    """

    pass
