from __future__ import annotations

from pathlib import Path

import pytest

from GENERAL.loadconfig import load_yaml_with_include, load_config
from GENERAL.errors import ConfigError, ConfigLoadError


def test_include_absent_returns_own_data(make_yaml):
    p = make_yaml(
        "cfg.yaml",
        """
        a: 1
        b: 2
        """,
    )
    assert load_yaml_with_include(p) == {"a": 1, "b": 2}


def test_include_single_overrides_base(make_yaml):
    base = make_yaml(
        "base.yaml",
        """
        a: 1
        b: 2
        """,
    )
    cfg = make_yaml(
        "cfg.yaml",
        """
        include: base.yaml
        b: 20
        c: 30
        """,
    )
    assert load_yaml_with_include(cfg) == {"a": 1, "b": 20, "c": 30}


def test_include_list_order_is_respected(make_yaml):
    make_yaml(
        "a.yaml",
        """
        x: 1
        y: 1
        """,
    )
    make_yaml(
        "b.yaml",
        """
        y: 2
        z: 2
        """,
    )
    cfg = make_yaml(
        "cfg.yaml",
        """
        include: [a.yaml, b.yaml]
        z: 999
        """,
    )

    # b.yaml переопределяет a.yaml для y; cfg.yaml переопределяет b.yaml для z
    assert load_yaml_with_include(cfg) == {"x": 1, "y": 2, "z": 999}


def test_include_cycle_is_detected(make_yaml):
    make_yaml(
        "a.yaml",
        """
        include: b.yaml
        a: 1
        """,
    )
    b = make_yaml(
        "b.yaml",
        """
        include: a.yaml
        b: 2
        """,
    )

    with pytest.raises(ConfigError) as e:
        load_yaml_with_include(b)

    assert "Циклический include" in str(e.value)


def test_invalid_yaml_raises_config_error(make_yaml):
    p = make_yaml("bad.yaml", "a: 1\n  b: 2\n")  # неправильные отступы / структура
    with pytest.raises(ConfigError):
        load_yaml_with_include(p)


def test_load_config_validation_error_is_wrapped(make_yaml, tmp_path: Path):
    # Минимальная модель Pydantic для теста
    from pydantic import BaseModel

    class Cfg(BaseModel):
        a: int

    cfg = make_yaml(
        "cfg.yaml",
        """
        a: not_an_int
        """,
    )

    with pytest.raises(ConfigLoadError):
        load_config(cfg, Cfg)
