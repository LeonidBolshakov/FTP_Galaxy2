from pathlib import Path
from dataclasses import FrozenInstanceError

import pytest

from DIGEST_APP.APP.dto import RuntimeContext, DescriptionOfNewTask
from DIGEST_APP.CONFIG.config import DigestConfig


def test_runtime_context_is_frozen():
    """Класс данных RuntimeContext должен быть заморожен (неизменяем)."""
    cfg = DigestConfig(local_dir=Path("/tmp"))
    ctx = RuntimeContext(app=cfg)
    # Попытка изменить поле должна привести к исключению FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        # noinspection PyDataclass
        ctx.app = None  # pytype: disable=attribute-error


def test_description_of_new_task_fields():
    """DescriptionOfNewTask должен хранить поля в том виде, в котором они были переданы."""
    d = DescriptionOfNewTask(
        task="T",
        first_solution="NEW",
        components=["C"],
        description="desc",
        what_has_changed="change",
        how_it_changed="how",
    )
    assert d.task == "T"
    assert d.components == ["C"]
