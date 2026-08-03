from app.inference.fire_detector import FireDetection
from app.models.schemas import AlarmSource, ObjectClass
from app.rules import alarm_trigger

HIT = [FireDetection(object_class=ObjectClass.SMOKE, confidence=0.9, bbox_xyxy=(0, 0, 10, 10))]
MISS: list[FireDetection] = []


def test_no_detections_does_not_trigger():
    assert alarm_trigger.evaluate("cam-1", []) is None


def test_single_hit_does_not_trigger_before_enough_samples():
    # 데모 시나리오에서 실측으로 발견한 버그: 표본이 아직 안 쌓인 상태에서 우연히
    # 배경 오탐 1건만 있어도 바로 경보가 울렸다 — consecutive_required(기본 2)보다
    # 적은 표본으론 절대 트리거하지 않아야 한다.
    assert alarm_trigger.evaluate("cam-1", [HIT]) is None


def test_two_consecutive_hits_trigger():
    alert = alarm_trigger.evaluate("cam-1", [HIT, HIT], confidence_threshold=0.6, consecutive_required=2)
    assert alert is not None
    assert alert.source == AlarmSource.AUTO_DETECTION
    assert alert.camera_id == "cam-1"


def test_hit_then_miss_does_not_trigger():
    # 연속이어야 한다 — 중간에 한 번 끊기면(단발 오탐 이후 사라짐) 트리거하지 않음
    assert alarm_trigger.evaluate("cam-1", [HIT, MISS], confidence_threshold=0.6, consecutive_required=2) is None


def test_only_the_last_n_samples_matter():
    # 예전에 히트가 있었어도, 최근 consecutive_required개 안에 미스가 섞이면 트리거 안 됨
    window = [HIT, HIT, HIT, MISS, HIT]  # 마지막 2개 = [MISS, HIT] → 연속 아님
    assert alarm_trigger.evaluate("cam-1", window, confidence_threshold=0.6, consecutive_required=2) is None


def test_low_confidence_hit_is_not_counted():
    low_conf = [FireDetection(object_class=ObjectClass.SMOKE, confidence=0.3, bbox_xyxy=(0, 0, 10, 10))]
    assert alarm_trigger.evaluate("cam-1", [low_conf, low_conf], confidence_threshold=0.6) is None


def test_consecutive_required_is_configurable():
    # consecutive_required=3으로 설정하면 2개 연속 히트로는 아직 부족해야 함
    assert alarm_trigger.evaluate("cam-1", [HIT, HIT], confidence_threshold=0.6, consecutive_required=3) is None
    alert = alarm_trigger.evaluate("cam-1", [HIT, HIT, HIT], confidence_threshold=0.6, consecutive_required=3)
    assert alert is not None


def test_manual_trigger_is_marked_as_manual_source():
    alert = alarm_trigger.manual_trigger("cam-1", "A구역", "2026-01-01T00:00:00")
    assert alert.source == AlarmSource.MANUAL
    assert alert.zone_id == "A구역"
