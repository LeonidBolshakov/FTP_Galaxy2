import pytest

from GENERAL.errors import (
    AppError,
    ConnectError,
    DownloadFileError,
    DownloadDirError,
    ConfigError,
    LocalFileAccessError,
    UserAbend,
    SkipExecute,
    ConfigLoadError,
    NewDirError,
)


def test_app_error_attributes():
    """Базовый класс AppError должен определять значения по умолчанию для exit_code и log_message."""
    err = AppError("boom")
    assert isinstance(err, Exception)
    # Default exit code and log message defined on the class
    assert hasattr(AppError, "exit_code") and AppError.exit_code == 1
    assert hasattr(AppError, "log_message")


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConnectError,
        DownloadFileError,
        DownloadDirError,
        ConfigError,
        LocalFileAccessError,
    ],
)
def test_subclasses_inherit_app_error(exc_cls):
    """Все пользовательские исключения, наследуемые от AppError, действительно должны быть его подклассами."""
    assert issubclass(exc_cls, AppError)


def test_local_file_access_error_is_oserror():
    """LocalFileAccessError также должен быть подклассом OSError."""
    assert issubclass(LocalFileAccessError, OSError)


def test_userabend_exit_code():
    """UserAbend должен переопределять exit_code."""
    assert UserAbend.exit_code == 130


def test_skipexecute_exit_code():
    """SkipExecute должен устанавливать уникальный exit_code и иметь docstring."""
    assert SkipExecute.exit_code == 777
    assert "закончить" in SkipExecute.__doc__.lower()


def test_configloaderror_and_newdirerror_are_plain_exceptions():
    """ConfigLoadError и NewDirError не должны наследоваться от AppError."""
    assert not issubclass(ConfigLoadError, AppError)
    assert not issubclass(NewDirError, AppError)
