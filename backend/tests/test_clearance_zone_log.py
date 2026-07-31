from app.models.schemas import ClearanceZoneState, ClearanceZoneStatus
from app.rules.clearance_zone_log import load_clearance_zone_log, record_if_changed


def test_no_log_on_first_call_with_no_prev_status(tmp_path, monkeypatch):
    import app.rules.clearance_zone_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    status = ClearanceZoneStatus(zone_id="panel-1", state=ClearanceZoneState.NORMAL)
    record_if_changed("cam-1", None, status, "2026-01-01T12:00:00")

    log = load_clearance_zone_log("cam-1", "panel-1")
    assert len(log) == 1
    assert log[0].state == ClearanceZoneState.NORMAL


def test_no_duplicate_log_when_state_unchanged(tmp_path, monkeypatch):
    import app.rules.clearance_zone_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    status = ClearanceZoneStatus(zone_id="panel-1", state=ClearanceZoneState.NORMAL)
    record_if_changed("cam-1", None, status, "2026-01-01T12:00:00")
    record_if_changed("cam-1", status, status, "2026-01-01T12:00:30")

    log = load_clearance_zone_log("cam-1", "panel-1")
    assert len(log) == 1


def test_new_log_entry_when_state_changes_and_carries_situation_note(tmp_path, monkeypatch):
    import app.rules.clearance_zone_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    normal = ClearanceZoneStatus(zone_id="panel-1", state=ClearanceZoneState.NORMAL)
    abnormal = ClearanceZoneStatus(
        zone_id="panel-1", state=ClearanceZoneState.ABNORMAL, situation_note="2차 확인(ZERO) 결과 우려 요소 발견: 쌓여있는 적재물"
    )

    record_if_changed("cam-1", None, normal, "2026-01-01T12:00:00")
    record_if_changed("cam-1", normal, abnormal, "2026-01-01T12:20:00")

    log = load_clearance_zone_log("cam-1", "panel-1")
    assert [e.state for e in log] == [ClearanceZoneState.NORMAL, ClearanceZoneState.ABNORMAL]
    assert log[1].situation_note == "2차 확인(ZERO) 결과 우려 요소 발견: 쌓여있는 적재물"
