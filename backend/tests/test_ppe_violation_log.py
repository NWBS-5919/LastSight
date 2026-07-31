from app.rules.ppe_violation_log import load_ppe_violation_log, record_if_newly_violated


def _record(track_id, *, was_violated_before, at, camera_id="cam-1", violation="helmet"):
    record_if_newly_violated(
        camera_id,
        track_id,
        violation=violation,
        was_violated_before=was_violated_before,
        zone="A구역",
        now_iso=at,
        frame_path=f"/demo-frames/frames/{at}.jpg",
        bbox_xyxy=(10.0, 20.0, 30.0, 40.0),
        confidence=0.9,
    )


def test_first_violation_is_logged(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record("P01", was_violated_before=False, at="2026-01-01T12:00:00")

    log = load_ppe_violation_log("cam-1", "P01")
    assert len(log) == 1
    assert log[0].violation == "helmet"
    assert log[0].frame_path == "/demo-frames/frames/2026-01-01T12:00:00.jpg"
    assert log[0].bbox_xyxy == (10.0, 20.0, 30.0, 40.0)


def test_continued_violation_is_not_logged_again(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record("P01", was_violated_before=False, at="2026-01-01T12:00:00")
    _record("P01", was_violated_before=True, at="2026-01-01T12:00:05")  # 계속 미착용 상태 지속

    log = load_ppe_violation_log("cam-1", "P01")
    assert len(log) == 1


def test_violation_ends_then_recurs_is_logged_again(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record("P01", was_violated_before=False, at="2026-01-01T12:00:00")  # 미착용 시작
    _record("P01", was_violated_before=False, at="2026-01-01T12:05:00")  # 착용했다가 다시 미착용

    log = load_ppe_violation_log("cam-1", "P01")
    assert len(log) == 2


def test_new_track_id_after_reappearance_logs_independently(tmp_path, monkeypatch):
    """추적 ID가 바뀌어도(같은 사람이 사라졌다 다시 나타나 새 ID를 받아도) 그냥 새
    위반 건으로 독립적으로 기록된다 — ID를 이어붙이려 하지 않는 게 의도된 동작."""
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record("P01", was_violated_before=False, at="2026-01-01T12:00:00")
    _record("P07", was_violated_before=False, at="2026-01-01T12:10:00")  # 새 ID, 같은 사람일 수도 있음

    assert len(load_ppe_violation_log("cam-1", "P01")) == 1
    assert len(load_ppe_violation_log("cam-1", "P07")) == 1


def test_helmet_and_vest_violations_tracked_independently(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record("P01", was_violated_before=False, at="2026-01-01T12:00:00", violation="helmet")
    _record("P01", was_violated_before=False, at="2026-01-01T12:00:00", violation="vest")

    log = load_ppe_violation_log("cam-1", "P01")
    assert {e.violation for e in log} == {"helmet", "vest"}
