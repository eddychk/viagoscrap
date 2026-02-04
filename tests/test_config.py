from viagoscrap.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("HEADLESS", raising=False)
    monkeypatch.delenv("TIMEOUT_MS", raising=False)
    cfg = Settings.from_env()
    assert cfg.headless is True
    assert cfg.timeout_ms == 30000
