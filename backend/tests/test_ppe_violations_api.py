from fastapi.testclient import TestClient

from app.main import app
from app.rules.ppe_violation_log import record_if_new_violation

client = TestClient(app)


def _patch_dirs(monkeypatch, tmp_path):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)


def test_list_ppe_violations_returns_sorted(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    record_if_new_violation(
        "cam-a", zone="B구역", violations=["vest"],
        now_iso="2026-01-01T12:05:00", frame_path="/f2.jpg", bbox_xyxy=(100, 100, 130, 140), confidence=0.8,
    )
    record_if_new_violation(
        "cam-a", zone="A구역", violations=["helmet"],
        now_iso="2026-01-01T12:00:00", frame_path="/f1.jpg", bbox_xyxy=(5, 6, 7, 8), confidence=0.9,
    )

    res = client.get("/ppe-violations/cam-a")
    assert res.status_code == 200
    body = res.json()
    assert [b["frame_path"] for b in body] == ["/f1.jpg", "/f2.jpg"]  # 시간순 정렬
    assert body[0]["bbox_xyxy"] == [5, 6, 7, 8]
    assert body[0]["violations"] == ["helmet"]


def test_incident_timeline_includes_ppe_violations(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    record_if_new_violation(
        "cam-b", zone="A구역", violations=["helmet"],
        now_iso="2026-01-01T09:00:00", frame_path="/f1.jpg", bbox_xyxy=(1, 1, 2, 2), confidence=0.9,
    )

    res = client.get("/incidents/cam-b/timeline")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["source"] == "ppe_violation"
    assert rows[0]["frame_path"] == "/f1.jpg"
    assert "헬멧 미착용 감지" in rows[0]["text"]


def test_ppe_settings_default_is_both_on(monkeypatch, tmp_path):
    import app.rules.ppe_settings as settings_module

    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)

    res = client.get("/ppe-settings/cam-c")
    assert res.status_code == 200
    body = res.json()
    assert body == {"camera_id": "cam-c", "detect_helmet": True, "detect_vest": True}


def test_ppe_settings_put_persists(monkeypatch, tmp_path):
    import app.rules.ppe_settings as settings_module

    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)

    res = client.put("/ppe-settings/cam-d", json={"camera_id": "cam-d", "detect_helmet": True, "detect_vest": False})
    assert res.status_code == 200

    res = client.get("/ppe-settings/cam-d")
    assert res.json() == {"camera_id": "cam-d", "detect_helmet": True, "detect_vest": False}
