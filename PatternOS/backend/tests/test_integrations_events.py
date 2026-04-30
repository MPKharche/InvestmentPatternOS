"""n8n / webhook emit helpers."""
from app.integrations import events as ev


def test_emit_sync_noop_without_url(monkeypatch):
    monkeypatch.setattr(ev, "_webhook_url", lambda: "")
    ev.emit_patternos_event_sync("t", {"a": 1})


def test_emit_sync_posts_when_configured(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(ev, "_webhook_url", lambda: "http://127.0.0.1:9/hook")
    monkeypatch.setattr(ev, "_headers", lambda: {"Content-Type": "application/json", "X-PatternOS-Secret": "x"})
    monkeypatch.setattr(ev.httpx, "post", fake_post)
    ev.emit_patternos_event_sync("equity_signal_created", {"symbol": "X"})

    assert len(calls) == 1
    assert calls[0][0] == "http://127.0.0.1:9/hook"
    assert calls[0][1]["json"] == {
        "event": "equity_signal_created",
        "payload": {"symbol": "X"},
    }
