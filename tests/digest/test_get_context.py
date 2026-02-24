from pathlib import Path
from types import SimpleNamespace

from DIGEST_APP.APP.dto import RuntimeContext
from DIGEST_APP.APP.SERVICES.get_context import GetContext
from DIGEST_APP.CONFIG.config import DigestConfig


def test_get_context_builds_runtime_context(monkeypatch):
    fake_args = SimpleNamespace(config=Path("config.yaml"))
    fake_config = object()
    calls: list[tuple[Path, type]] = []

    monkeypatch.setattr(
        "DIGEST_APP.APP.SERVICES.get_context.parse_args",
        lambda: fake_args,
    )

    def fake_load_config(path: Path, cls: type):
        calls.append((path, cls))
        return fake_config

    monkeypatch.setattr(
        "DIGEST_APP.APP.SERVICES.get_context.load_config",
        fake_load_config,
    )

    ctx = GetContext().run()

    assert calls == [(fake_args.config, DigestConfig)]
    assert isinstance(ctx, RuntimeContext)
    assert ctx.app is fake_config
