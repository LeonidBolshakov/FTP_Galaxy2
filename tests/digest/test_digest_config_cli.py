from pathlib import Path
import sys

import pytest

from DIGEST_APP.CONFIG import config_CLI
from GENERAL.errors import ConfigError


def test_parse_args_returns_path(monkeypatch):
    """Функция parse_args должна разобрать позиционный аргумент конфигурации и вернуть Namespace с объектом Path."""
    # Подготавливаем фиктивный argv с именем программы и путём к конфигурации
    fake_argv = ["prog", "/tmp/config.yaml"]
    monkeypatch.setattr(sys, "argv", fake_argv)
    args = config_CLI.parse_args()
    assert isinstance(args.config, Path)
    assert args.config == Path("/tmp/config.yaml")


def test_parse_args_invalid_raises_configerror(monkeypatch):
    """Если argparse обнаруживает ошибку, parse_args должен поднять исключение ConfigError."""
    # Не передаем аргумент конфигурации, чтобы вызвать ошибку argparse
    fake_argv = ["prog"]
    monkeypatch.setattr(sys, "argv", fake_argv)
    with pytest.raises(ConfigError):
        config_CLI.parse_args()
