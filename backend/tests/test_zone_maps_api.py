from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_zone_map_returns_empty_default_for_unknown_camera():
    res = client.get("/zone-maps/no-such-camera")
    assert res.status_code == 200
    body = res.json()
    assert body["camera_id"] == "no-such-camera"
    assert body["zones"] == []
    assert body["clearance_zones"] == []


def test_put_then_get_zone_map_roundtrip(tmp_path, monkeypatch):
    import app.rules.zone as zone_module

    monkeypatch.setattr(zone_module, "ZONE_MAP_DIR", tmp_path)

    payload = {
        "camera_id": "test-cam",
        "image_width": 100,
        "image_height": 100,
        "zones": [{"zone_id": "A", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
    }
    put_res = client.put("/zone-maps/test-cam", json=payload)
    assert put_res.status_code == 200

    get_res = client.get("/zone-maps/test-cam")
    assert get_res.status_code == 200
    assert get_res.json()["zones"][0]["zone_id"] == "A"


def test_reference_image_404_when_not_uploaded():
    res = client.get("/zone-maps/no-image-camera/reference-image")
    assert res.status_code == 404
