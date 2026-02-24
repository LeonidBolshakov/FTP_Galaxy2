from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Включает src в path
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture()
def make_yaml(tmp_path: Path):
    """Helper быстрого создания YAML файла во временной директории."""

    def _make(name: str, text: str) -> Path:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        return p

    return _make


@pytest.fixture()
def digest_ctx(tmp_path: Path):
    """Минимальный ctx для DIGEST сервисов (утиная типизация;
    полная конфигурация Pydantic не требуется)."""

    new_dir = tmp_path / "NEW"  # путь есть, каталога нет
    # GetDescriptionOfNewTasks использует ctx.app.new_dir
    app = SimpleNamespace(new_dir=new_dir)

    # RuntimeContext — это класс данных, который хранит только содержимое файла .app;
    # мы можем использовать его напрямую.
    from DIGEST_APP.APP.dto import RuntimeContext

    return RuntimeContext(app=app)


@pytest.fixture()
def digest_ctx_with_new(tmp_path: Path):
    new_dir = tmp_path / "NEW"
    new_dir.mkdir(parents=True, exist_ok=True)
    app = SimpleNamespace(new_dir=new_dir)

    from DIGEST_APP.APP.dto import RuntimeContext

    return RuntimeContext(app=app)


@pytest.fixture()
def sync_ctx():
    """Минимальный ctx для SYNC сервисов (утиная типизация; полная конфигурация Pydantic не требуется)."""
    # DiffPlanner использует ctx.app.add_list / stop_list + ctx.mode_stop_list
    app = SimpleNamespace(add_list=[], stop_list=[])
    from SYNC_APP.APP.dto import RuntimeContext
    from SYNC_APP.APP.types import ModeDiffPlan

    return RuntimeContext(
        app=app, once_per_day=False, mode_stop_list=ModeDiffPlan.NOT_USE_STOP_LIST
    )
