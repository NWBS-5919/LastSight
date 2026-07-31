from app.inference.fire_detector import FireDetection
from app.models.schemas import AlarmSource, ObjectClass
from app.rules import alarm_trigger

HIT = [FireDetection(object_class=ObjectClass.SMOKE, confidence=0.9, bbox_xyxy=(0, 0, 10, 10))]
MISS: list[FireDetection] = []


def test_no_detections_does_not_trigger():
    assert alarm_trigger.evaluate("cam-1", []) is None


def test_single_early_hit_does_not_trigger_before_window_fills():
    # 데모 시나리오에서 실측으로 발견한 버그: 윈도우가 아직 안 채워진 상태(표본 1개)에서
    # 우연히 배경 오탐 1건만 있어도 히트율이 100%가 되어 바로 경보가 울렸다.
    assert alarm_trigger.evaluate("cam-1", [HIT], min_window_size=5) is None
    assert alarm_trigger.evaluate("cam-1", [HIT, HIT], min_window_size=5) is None


def test_sustained_hits_across_full_window_triggers():
    window = [HIT, HIT, HIT, MISS, MISS]  # 5프레임 중 3개 히트 = 60%
    alert = alarm_trigger.evaluate("cam-1", window, confidence_threshold=0.6, min_hit_ratio=0.6, min_window_size=5)
    assert alert is not None
    assert alert.source == AlarmSource.AUTO_DETECTION
    assert alert.camera_id == "cam-1"


def test_isolated_hit_within_full_window_does_not_trigger():
    window = [HIT, MISS, MISS, MISS, MISS]  # 5프레임 중 1개 히트 = 20% < 60%
    assert alarm_trigger.evaluate("cam-1", window, confidence_threshold=0.6, min_hit_ratio=0.6, min_window_size=5) is None


def test_low_confidence_hit_is_not_counted():
    low_conf = [FireDetection(object_class=ObjectClass.SMOKE, confidence=0.3, bbox_xyxy=(0, 0, 10, 10))]
    window = [low_conf] * 5
    assert alarm_trigger.evaluate("cam-1", window, confidence_threshold=0.6, min_window_size=5) is None


def test_manual_trigger_is_marked_as_manual_source():
    alert = alarm_trigger.manual_trigger("cam-1", "A구역", "2026-01-01T00:00:00")
    assert alert.source == AlarmSource.MANUAL
    assert alert.zone_id == "A구역"
