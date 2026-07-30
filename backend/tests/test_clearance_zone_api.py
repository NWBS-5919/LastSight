import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ZONE_POLYGON = [[50, 50], [150, 50], [150, 150], [50, 150]]


def _jpeg_bytes(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _blank_image() -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.random((200, 200, 3)) * 20 + 100).astype(np.uint8)


def _image_with_block() -> np.ndarray:
    img = _blank_image()
    img[70:130, 70:130] = (10, 10, 10)
    return img


def _patch_dirs(monkeypatch, tmp_path):
    import app.rules.clearance_zone as cz_module
    import app.rules.zone as zone_module

    monkeypatch.setattr(zone_module, "ZONE_MAP_DIR", tmp_path / "zone_maps")
    monkeypatch.setattr(cz_module, "STATUS_DIR", tmp_path / "clearance_status")
    monkeypatch.setattr(cz_module, "BASELINE_DIR", tmp_path / "clearance_baselines")


def _register_camera_with_zone(camera_id: str) -> None:
    payload = {
        "camera_id": camera_id,
        "clearance_zones": [
            {"zone_id": "panel-1", "zone_type": "electrical_panel", "polygon": ZONE_POLYGON, "label": "배전반 A"}
        ],
    }
    res = client.put(f"/zone-maps/{camera_id}", json=payload)
    assert res.status_code == 200


def test_baseline_upload_sets_normal_status(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _register_camera_with_zone("cam-a")

    res = client.post(
        "/zone-maps/cam-a/clearance-zones/panel-1/baseline",
        files={"file": ("baseline.jpg", _jpeg_bytes(_blank_image()), "image/jpeg")},
    )
    assert res.status_code == 200
    assert res.json()["state"] == "normal"

    status_res = client.get("/zone-maps/cam-a/clearance-zones/status")
    assert status_res.json()["panel-1"]["state"] == "normal"


def test_baseline_upload_for_unknown_zone_is_404(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _register_camera_with_zone("cam-b")

    res = client.post(
        "/zone-maps/cam-b/clearance-zones/no-such-zone/baseline",
        files={"file": ("baseline.jpg", _jpeg_bytes(_blank_image()), "image/jpeg")},
    )
    assert res.status_code == 404


def test_evaluate_without_baseline_is_400(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _register_camera_with_zone("cam-c")

    res = client.post(
        "/zone-maps/cam-c/clearance-zones/panel-1/evaluate",
        files={"file": ("frame.jpg", _jpeg_bytes(_blank_image()), "image/jpeg")},
    )
    assert res.status_code == 400


def test_evaluate_detects_change_then_resolve_clears_it(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _register_camera_with_zone("cam-d")

    client.post(
        "/zone-maps/cam-d/clearance-zones/panel-1/baseline",
        files={"file": ("baseline.jpg", _jpeg_bytes(_blank_image()), "image/jpeg")},
    )

    eval_res = client.post(
        "/zone-maps/cam-d/clearance-zones/panel-1/evaluate",
        files={"file": ("frame.jpg", _jpeg_bytes(_image_with_block()), "image/jpeg")},
    )
    assert eval_res.status_code == 200
    assert eval_res.json()["state"] == "observing"

    resolve_res = client.post("/zone-maps/cam-d/clearance-zones/panel-1/resolve")
    assert resolve_res.status_code == 200
    assert resolve_res.json()["state"] == "normal"

    status_res = client.get("/zone-maps/cam-d/clearance-zones/status")
    assert status_res.json()["panel-1"]["state"] == "normal"


def test_evaluate_ignores_change_when_person_overlaps_zone(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _register_camera_with_zone("cam-e")

    client.post(
        "/zone-maps/cam-e/clearance-zones/panel-1/baseline",
        files={"file": ("baseline.jpg", _jpeg_bytes(_blank_image()), "image/jpeg")},
    )

    res = client.post(
        "/zone-maps/cam-e/clearance-zones/panel-1/evaluate",
        files={"file": ("frame.jpg", _jpeg_bytes(_image_with_block()), "image/jpeg")},
        data={"person_boxes": "[[60, 60, 140, 140]]"},
    )
    assert res.status_code == 200
    assert res.json()["state"] == "normal"  # 사람이 겹쳐 있으니 변화 판정 자체를 보류
