from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import (
    AlarmSource,
    ClearanceZoneState,
    ClearanceZoneStatus,
    FireAlert,
    WorkerEvent,
    WorkerStatus,
)
from app.rules.clearance_zone_log import record_if_changed as record_clearance_zone_log
from app.rules.fire_alert_log import append_fire_alert
from app.rules.worker_log import record_if_changed as record_worker_log

client = TestClient(app)


def _patch_dirs(monkeypatch, tmp_path):
    import app.api.incidents as incidents_module
    import app.rules.clearance_zone_log as clearance_log_module
    import app.rules.fire_alert_log as fire_log_module
    import app.rules.worker_log as worker_log_module

    monkeypatch.setattr(fire_log_module, "LOG_DIR", tmp_path / "fire_alerts")
    monkeypatch.setattr(worker_log_module, "LOG_DIR", tmp_path / "worker_logs")
    monkeypatch.setattr(clearance_log_module, "LOG_DIR", tmp_path / "clearance_zone_logs")
    monkeypatch.setattr(incidents_module, "WORKER_LOG_DIR", tmp_path / "worker_logs")
    monkeypatch.setattr(incidents_module, "CLEARANCE_LOG_DIR", tmp_path / "clearance_zone_logs")


def _seed_incident(camera_id: str) -> None:
    append_fire_alert(
        FireAlert(camera_id=camera_id, zone_id="A구역", triggered_at="2026-01-01T12:00:00", source=AlarmSource.AUTO_DETECTION, confidence=0.9)
    )

    inside = WorkerStatus(track_id="P01", event=WorkerEvent.INSIDE_OBSERVED, last_zone="A구역")
    prolonged = WorkerStatus(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="A구역")
    record_worker_log(camera_id, None, inside, "2026-01-01T11:55:00")
    record_worker_log(camera_id, inside, prolonged, "2026-01-01T12:10:00")

    normal = ClearanceZoneStatus(zone_id="ext-1", state=ClearanceZoneState.NORMAL)
    abnormal = ClearanceZoneStatus(zone_id="ext-1", state=ClearanceZoneState.ABNORMAL, situation_note="쌓여있는 적재물")
    record_clearance_zone_log(camera_id, None, normal, "2026-01-01T11:50:00")
    record_clearance_zone_log(camera_id, normal, abnormal, "2026-01-01T12:05:00")


def test_timeline_merges_and_sorts_all_sources(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _seed_incident("cam-timeline")

    res = client.get("/incidents/cam-timeline/timeline")
    assert res.status_code == 200
    rows = res.json()

    ats = [r["at"] for r in rows]
    assert ats == sorted(ats)  # 시간순 정렬
    sources = {r["source"] for r in rows}
    assert sources == {"fire_alert", "worker", "clearance_zone"}
    assert len(rows) == 5  # fire_alert 1 + worker 2(inside_observed→prolonged) + clearance_zone 2(normal→abnormal)


def test_state_at_reconstructs_snapshot_before_prolonged_presence(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _seed_incident("cam-state")

    res = client.get("/incidents/cam-state/state-at", params={"at": "2026-01-01T12:02:00"})
    assert res.status_code == 200
    snap = res.json()

    assert snap["fire_alert"]["zone_id"] == "A구역"
    assert snap["workers"]["P01"]["event"] == "inside_observed"  # 아직 prolonged 전
    assert snap["clearance_zones"]["ext-1"]["state"] == "normal"  # abnormal 전환(12:05) 이전이라 아직 normal


def test_state_at_after_all_transitions(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _seed_incident("cam-state-2")

    res = client.get("/incidents/cam-state-2/state-at", params={"at": "2026-01-01T12:30:00"})
    snap = res.json()

    assert snap["workers"]["P01"]["event"] == "prolonged_presence"
    assert snap["clearance_zones"]["ext-1"]["state"] == "abnormal"
    assert snap["clearance_zones"]["ext-1"]["situation_note"] == "쌓여있는 적재물"
