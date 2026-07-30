from app.models.schemas import WorkerEvent, WorkerStatus
from app.rules.worker_log import load_worker_log, record_if_changed


def test_no_log_on_first_call_with_no_prev_status(tmp_path, monkeypatch):
    import app.rules.worker_log as worker_log_module

    monkeypatch.setattr(worker_log_module, "LOG_DIR", tmp_path)

    status = WorkerStatus(track_id="P01", event=WorkerEvent.INSIDE_OBSERVED, last_zone="A")
    record_if_changed("cam-1", None, status, "2026-01-01T12:00:00")

    log = load_worker_log("cam-1", "P01")
    assert len(log) == 1
    assert log[0].event == WorkerEvent.INSIDE_OBSERVED


def test_no_duplicate_log_when_event_unchanged(tmp_path, monkeypatch):
    import app.rules.worker_log as worker_log_module

    monkeypatch.setattr(worker_log_module, "LOG_DIR", tmp_path)

    status = WorkerStatus(track_id="P01", event=WorkerEvent.INSIDE_OBSERVED, last_zone="A")
    record_if_changed("cam-1", None, status, "2026-01-01T12:00:00")
    record_if_changed("cam-1", status, status, "2026-01-01T12:00:30")  # 동일 이벤트 반복

    log = load_worker_log("cam-1", "P01")
    assert len(log) == 1  # 중복 기록 안 됨


def test_new_log_entry_when_event_changes(tmp_path, monkeypatch):
    import app.rules.worker_log as worker_log_module

    monkeypatch.setattr(worker_log_module, "LOG_DIR", tmp_path)

    inside = WorkerStatus(track_id="P01", event=WorkerEvent.INSIDE_OBSERVED, last_zone="A")
    prolonged = WorkerStatus(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="A")

    record_if_changed("cam-1", None, inside, "2026-01-01T12:00:00")
    record_if_changed("cam-1", inside, prolonged, "2026-01-01T12:05:00")

    log = load_worker_log("cam-1", "P01")
    assert [e.event for e in log] == [WorkerEvent.INSIDE_OBSERVED, WorkerEvent.PROLONGED_PRESENCE]
    assert log[1].at == "2026-01-01T12:05:00"
