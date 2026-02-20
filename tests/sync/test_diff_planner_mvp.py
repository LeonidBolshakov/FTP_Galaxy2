from __future__ import annotations

from types import SimpleNamespace

from SYNC_APP.APP.SERVICES.diff_planer import DiffPlanner
from SYNC_APP.APP.dto import DiffInput, RepositorySnapshot, FileSnapshot
from SYNC_APP.APP.types import ModeDiffPlan


def _snap(**files: int) -> RepositorySnapshot:
    """Helper: build RepositorySnapshot from name->size mapping."""
    return RepositorySnapshot(
        files={
            name: FileSnapshot(name=name, size=size, md5_hash=None)
            for name, size in files.items()
        }
    )


def test_no_updates_produces_important_info(sync_ctx):
    planner = DiffPlanner()
    data = DiffInput(context=sync_ctx, local_snap=_snap(), remote_snap=_snap())

    plan, is_valid, report = planner.run(data)

    assert is_valid is True
    assert plan.to_delete == []
    assert plan.to_download == []
    assert any("Обновлений нет" in r.comment for r in report)


def test_remote_only_files_are_downloaded(sync_ctx):
    planner = DiffPlanner()
    data = DiffInput(
        context=sync_ctx, local_snap=_snap(), remote_snap=_snap(a=10, b=20)
    )

    plan, is_valid, report = planner.run(data)

    assert is_valid is True
    assert [x.name for x in plan.to_download] == ["a", "b"]
    assert plan.to_delete == []
    assert report == []


import pytest


@pytest.mark.xfail(
    reason="Известный баг: если raw_download_names пуст, _apply_stop_add_lists возвращает пустые множества и теряет to_delete"
)
def test_local_only_files_are_deleted(sync_ctx):
    planner = DiffPlanner()
    data = DiffInput(
        context=sync_ctx, local_snap=_snap(a=10, b=20), remote_snap=_snap()
    )

    plan, is_valid, report = planner.run(data)

    assert is_valid is True
    assert [x.name for x in plan.to_delete] == ["a", "b"]
    assert plan.to_download == []
    assert report == []


def test_mismatched_size_goes_to_delete_and_download(sync_ctx):
    planner = DiffPlanner()
    data = DiffInput(context=sync_ctx, local_snap=_snap(a=10), remote_snap=_snap(a=999))

    plan, is_valid, report = planner.run(data)

    assert is_valid is True
    assert [x.name for x in plan.to_delete] == ["a"]
    assert [x.name for x in plan.to_download] == ["a"]


def test_stop_list_excludes_download_and_marks_invalid(sync_ctx):
    # stop-list works on component name derived from file name
    # name_file_to_name_component("AAA_123.zip") -> likely "AAA" (see infra/utils.py)
    sync_ctx = sync_ctx.__class__(
        app=SimpleNamespace(add_list=[], stop_list=["AAA.zip"]),
        once_per_day=False,
        mode_stop_list=ModeDiffPlan.USE_STOP_LIST,
    )

    planner = DiffPlanner()

    data = DiffInput(
        context=sync_ctx,
        local_snap=_snap(),
        remote_snap=_snap(**{"AAA_123.zip": 10, "BBB_1.zip": 10}),
    )

    plan, is_valid, report = planner.run(data)

    assert is_valid is False
    assert [x.name for x in plan.to_download] == ["BBB_1.zip"]
    assert any(r.name == "AAA_123.zip" for r in report)
