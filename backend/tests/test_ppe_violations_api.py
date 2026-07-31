from fastapi.testclient import TestClient

from app.main import app
from app.rules.ppe_violation_log import record_if_newly_violated

client = TestClient(app)


def _patch_dirs(monkeypatch, tmp_path):
    import app.api.incidents as incidents_module
    import app.api.ppe as ppe_module
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)
    monkeypatch.setattr(ppe_module, "PPE_VIOLATION_LOG_DIR", tmp_path)
    monkeypatch.setattr(incidents_module, "PPE_VIOLATION_LOG_DIR", tmp_path)


def test_list_ppe_violations_returns_sorted_across_tracks(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    record_if_newly_violated(
        "cam-a", "P02", violation="vest", was_violated_before=False, zone="B구역",
        now_iso="2026-01-01T12:05:00", frame_path="/f2.jpg", bbox_xyxy=(1, 2, 3, 4), confidence=0.8,
    )
    record_if_newly_violated(
        "cam-a", "P01", violation="helmet", was_violated_before=False, zone="A구역",
        now_iso="2026-01-01T12:00:00", frame_path="/f1.jpg", bbox_xyxy=(5, 6, 7, 8), confidence=0.9,
    )

    res = client.get("/ppe-violations/cam-a")
    assert res.status_code == 200
    body = res.json()
    assert [b["track_id"] for b in body] == ["P01", "P02"]  # 시간순 정렬
    assert body[0]["frame_path"] == "/f1.jpg"
    assert body[0]["bbox_xyxy"] == [5, 6, 7, 8]


def test_incident_timeline_includes_ppe_violations(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    record_if_newly_violated(
        "cam-b", "P01", violation="helmet", was_violated_before=False, zone="A구역",
        now_iso="2026-01-01T09:00:00", frame_path="/f1.jpg", bbox_xyxy=(1, 1, 2, 2), confidence=0.9,
    )

    res = client.get("/incidents/cam-b/timeline")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["source"] == "ppe_violation"
    assert rows[0]["frame_path"] == "/f1.jpg"
    assert "helmet 미착용 감지" in rows[0]["text"]
