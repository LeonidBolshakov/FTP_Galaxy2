from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# --- ������� `src/` ������������� � ������ -------------------------------------------------
# ��������� ������� �� ������: /<repo_root>/src/{GENERAL,SYNC_APP,DIGEST_APP}
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture()
def make_yaml(tmp_path: Path):
    """Helper to quickly create YAML files in a temp dir."""

    def _make(name: str, text: str) -> Path:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        return p

    return _make


@pytest.fixture()
def digest_ctx(tmp_path: Path):
    """Minimal ctx for DIGEST services (duck-typed; no need for full Pydantic config)."""
    new_dir = tmp_path / "NEW"
    # ctx.app.new_dir is used by GetDescriptionOfNewTasks
    app = SimpleNamespace(new_dir=str(new_dir))

    # RuntimeContext is a dataclass that only stores .app; we can use it directly
    from DIGEST_APP.APP.dto import RuntimeContext

    return RuntimeContext(app=app)


@pytest.fixture()
def sync_ctx():
    """Minimal ctx for SYNC services (duck-typed; no need for full SyncConfig)."""
    # DiffPlanner ���������� ctx.app.add_list / stop_list + ctx.mode_stop_list
    app = SimpleNamespace(add_list=[], stop_list=[])
    from SYNC_APP.APP.dto import RuntimeContext
    from SYNC_APP.APP.types import ModeDiffPlan

    return RuntimeContext(
        app=app, once_per_day=False, mode_stop_list=ModeDiffPlan.NOT_USE_STOP_LIST
    )
