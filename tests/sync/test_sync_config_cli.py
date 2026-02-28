from pathlib import Path
import sys

import pytest

from SYNC_APP.CONFIG import config_CLI
from GENERAL.errors import ConfigError
from SYNC_APP.APP.types import ModeDiffPlan


def test_mode_type_valid_options():
    assert config_CLI.mode_type("stop-list") is ModeDiffPlan.USE_STOP_LIST
    assert config_CLI.mode_type("no-list") is ModeDiffPlan.NOT_USE_STOP_LIST
    # case-insensitive and surrounding spaces
    assert config_CLI.mode_type("  STOP-LIST  ") is ModeDiffPlan.USE_STOP_LIST


def test_mode_type_invalid_option():
    with pytest.raises(Exception):
        config_CLI.mode_type("invalid")


def test_parse_args_returns_expected(monkeypatch):
    """Функция parse_args должна разобрать путь к конфигурации, флаг once_per_day и параметр режима."""
    argv = ["prog", "/tmp/cfg.yaml", "--once-per-day", "--mode", "stop-list"]
    monkeypatch.setattr(sys, "argv", argv)
    args = config_CLI.parse_args()
    assert args.config == Path("/tmp/cfg.yaml")
    assert args.once_per_day is True
    assert args.mode is ModeDiffPlan.USE_STOP_LIST


def test_parse_args_missing_config(monkeypatch):
    argv = ["prog", "--once-per-day"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(ConfigError):
        config_CLI.parse_args()
