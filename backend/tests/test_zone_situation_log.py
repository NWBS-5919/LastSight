from app.models.schemas import ZoneSituationBox, ZoneSituationEntry, ZoneSituationLogEntry
from app.rules.zone_situation_log import append_zone_situation, load_zone_situation_log


def _entry(camera_id="cam-1", at="2026-01-01T12:00:00", frame_path="/f1.jpg"):
    return ZoneSituationLogEntry(
        camera_id=camera_id,
        at=at,
        zones=[
            ZoneSituationEntry(
                zone_id="A구역",
                total=4,
                breakdown={"체류중": 1, "쓰러진 사람": 3},
                boxes=[
                    ZoneSituationBox(category="체류중", bbox_xyxy=(0, 0, 10, 10)),
                    ZoneSituationBox(category="쓰러진 사람", bbox_xyxy=(20, 20, 30, 30)),
                    ZoneSituationBox(category="쓰러진 사람", bbox_xyxy=(40, 40, 50, 50)),
                    ZoneSituationBox(category="쓰러진 사람", bbox_xyxy=(60, 60, 70, 70)),
                ],
            ),
            ZoneSituationEntry(zone_id="B구역", total=2, breakdown={"체류중": 1, "연기에 둘러싸인 사람": 1}),
        ],
        frame_path=frame_path,
    )


def test_append_and_load_roundtrip(tmp_path, monkeypatch):
    import app.rules.zone_situation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    append_zone_situation(_entry())

    log = load_zone_situation_log("cam-1")
    assert len(log) == 1
    assert log[0].zones[0].zone_id == "A구역"
    assert log[0].zones[0].breakdown == {"체류중": 1, "쓰러진 사람": 3}
    assert len(log[0].zones[0].boxes) == log[0].zones[0].total == 4
    assert [b.category for b in log[0].zones[0].boxes] == ["체류중", "쓰러진 사람", "쓰러진 사람", "쓰러진 사람"]


def test_boxes_field_defaults_to_empty_list(tmp_path, monkeypatch):
    import app.rules.zone_situation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    append_zone_situation(_entry())

    log = load_zone_situation_log("cam-1")
    assert log[0].zones[1].zone_id == "B구역"
    assert log[0].zones[1].boxes == []


def test_entries_accumulate_in_order(tmp_path, monkeypatch):
    import app.rules.zone_situation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    append_zone_situation(_entry(at="2026-01-01T12:00:00"))
    append_zone_situation(_entry(at="2026-01-01T12:05:00"))

    log = load_zone_situation_log("cam-1")
    assert [e.at for e in log] == ["2026-01-01T12:00:00", "2026-01-01T12:05:00"]


def test_different_cameras_are_isolated(tmp_path, monkeypatch):
    import app.rules.zone_situation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    append_zone_situation(_entry(camera_id="cam-a"))
    append_zone_situation(_entry(camera_id="cam-b"))

    assert len(load_zone_situation_log("cam-a")) == 1
    assert len(load_zone_situation_log("cam-b")) == 1


def test_load_missing_camera_returns_empty_list(tmp_path, monkeypatch):
    import app.rules.zone_situation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    assert load_zone_situation_log("no-such-camera") == []
