from app.models.schemas import AlarmSource, FireAlert
from app.rules.fire_alert_log import append_fire_alert, latest_fire_alert, load_fire_alerts


def _patch(monkeypatch, tmp_path):
    import app.rules.fire_alert_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)


def test_load_empty_when_no_alerts(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    assert load_fire_alerts("cam-1") == []
    assert latest_fire_alert("cam-1") is None


def test_append_and_load_roundtrip(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    alert = FireAlert(camera_id="cam-1", zone_id="B구역", triggered_at="2026-01-01T12:00:00", source=AlarmSource.AUTO_DETECTION, confidence=0.91)
    append_fire_alert(alert)

    alerts = load_fire_alerts("cam-1")
    assert len(alerts) == 1
    assert alerts[0].zone_id == "B구역"


def test_latest_alert_picks_most_recent(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    append_fire_alert(FireAlert(camera_id="cam-1", triggered_at="2026-01-01T12:00:00", source=AlarmSource.AUTO_DETECTION))
    append_fire_alert(FireAlert(camera_id="cam-1", triggered_at="2026-01-01T12:10:00", source=AlarmSource.MANUAL))

    latest = latest_fire_alert("cam-1")
    assert latest is not None
    assert latest.triggered_at == "2026-01-01T12:10:00"
