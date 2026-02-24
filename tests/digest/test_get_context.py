from pathlib import Path
from types import SimpleNamespace

from DIGEST_APP.APP.dto import RuntimeContext
from DIGEST_APP.APP.SERVICES.get_context import GetContext


def test_get_context_builds_runtime_context(monkeypatch):
    fake_args = SimpleNamespace(config=Path("config.yaml"))
    fake_config = object()

    monkeypatch.setattr(
        "DIGEST_APP.CONFIG.config_CLI.parse_args",
        lambda: fake_args,
    )

    monkeypatch.setattr(
        "GENERAL.loadconfig.load_config",
        lambda path, cls: fake_config,
    )

    ctx = GetContext().run()

    assert isinstance(ctx, RuntimeContext)
    assert ctx.app is fake_config
