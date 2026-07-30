from datetime import datetime, timedelta

import numpy as np

from app.models.schemas import ClearanceZoneDef, ClearanceZoneState, ClearanceZoneType
from app.rules.clearance_zone import evaluate_clearance_zone

ZONE_POLYGON = [(50, 50), (150, 50), (150, 150), (50, 150)]
NOW = datetime(2026, 1, 1, 12, 0, 0)
PAST_PERSIST_WINDOW = timedelta(minutes=20)  # PERSIST_SECONDS(15분)를 확실히 넘기는 경과 시간


def _panel_zone() -> ClearanceZoneDef:
    return ClearanceZoneDef(zone_id="Z1", zone_type=ClearanceZoneType.ELECTRICAL_PANEL, polygon=ZONE_POLYGON)


def _extinguisher_zone() -> ClearanceZoneDef:
    return ClearanceZoneDef(zone_id="Z2", zone_type=ClearanceZoneType.FIRE_EXTINGUISHER, polygon=ZONE_POLYGON)


def _blank_frame() -> np.ndarray:
    rng = np.random.default_rng(0)
    # 완전 단색이면 SSIM 분모가 0에 가까워 불안정하므로 약한 텍스처를 준다
    return (rng.random((200, 200, 3)) * 20 + 100).astype(np.uint8)


def _frame_with_block_in_zone(base: np.ndarray) -> np.ndarray:
    out = base.copy()
    out[70:130, 70:130] = (10, 10, 10)  # 구역 안(100x100 중 60x60 = 36%)에 진한 사각 블록
    return out


def test_no_change_is_normal():
    base = _blank_frame()
    status = evaluate_clearance_zone(_panel_zone(), prev_status=None, now=NOW, current_frame=base, baseline_frame=base)
    assert status.state == ClearanceZoneState.NORMAL


def test_new_change_starts_observing_not_immediately_abnormal():
    base = _blank_frame()
    changed = _frame_with_block_in_zone(base)
    status = evaluate_clearance_zone(
        _panel_zone(), prev_status=None, now=NOW, current_frame=changed, baseline_frame=base
    )
    assert status.state == ClearanceZoneState.OBSERVING
    assert status.changed_since == NOW.isoformat()


def test_sustained_change_becomes_abnormal():
    base = _blank_frame()
    changed = _frame_with_block_in_zone(base)
    first = evaluate_clearance_zone(_panel_zone(), prev_status=None, now=NOW, current_frame=changed, baseline_frame=base)

    later = NOW + PAST_PERSIST_WINDOW
    second = evaluate_clearance_zone(
        _panel_zone(), prev_status=first, now=later, current_frame=changed, baseline_frame=base
    )
    assert second.state == ClearanceZoneState.ABNORMAL
    assert second.changed_since == NOW.isoformat()  # 최초 감지 시각을 계속 유지


def test_change_disappearing_resets_to_normal():
    base = _blank_frame()
    changed = _frame_with_block_in_zone(base)
    observing = evaluate_clearance_zone(
        _panel_zone(), prev_status=None, now=NOW, current_frame=changed, baseline_frame=base
    )

    later = NOW + PAST_PERSIST_WINDOW
    recovered = evaluate_clearance_zone(
        _panel_zone(), prev_status=observing, now=later, current_frame=base, baseline_frame=base
    )
    assert recovered.state == ClearanceZoneState.NORMAL
    assert recovered.changed_since is None


def test_person_overlapping_zone_holds_previous_state():
    base = _blank_frame()
    changed = _frame_with_block_in_zone(base)
    observing = evaluate_clearance_zone(
        _panel_zone(), prev_status=None, now=NOW, current_frame=changed, baseline_frame=base
    )

    later = NOW + PAST_PERSIST_WINDOW
    held = evaluate_clearance_zone(
        _panel_zone(),
        prev_status=observing,
        now=later,
        current_frame=changed,
        baseline_frame=base,
        person_boxes=[(60, 60, 140, 140)],  # 구역과 겹치는 사람 박스
    )
    assert held.state == ClearanceZoneState.OBSERVING  # ABNORMAL로 승격되지 않고 이전 상태 유지
    assert held.changed_since == observing.changed_since


def test_missing_baseline_is_camera_failure():
    base = _blank_frame()
    status = evaluate_clearance_zone(_panel_zone(), prev_status=None, now=NOW, current_frame=base, baseline_frame=None)
    assert status.state == ClearanceZoneState.CAMERA_FAILURE


def test_fire_extinguisher_zone_uses_same_change_detection():
    # 소화기도 별도 탐지 모델 없이 전기패널/비상구와 완전히 같은 변화 감지 로직을 탄다.
    base = _blank_frame()
    status = evaluate_clearance_zone(
        _extinguisher_zone(), prev_status=None, now=NOW, current_frame=base, baseline_frame=base
    )
    assert status.state == ClearanceZoneState.NORMAL

    changed = _frame_with_block_in_zone(base)
    first = evaluate_clearance_zone(
        _extinguisher_zone(), prev_status=None, now=NOW, current_frame=changed, baseline_frame=base
    )
    assert first.state == ClearanceZoneState.OBSERVING

    later = NOW + PAST_PERSIST_WINDOW
    second = evaluate_clearance_zone(
        _extinguisher_zone(), prev_status=first, now=later, current_frame=changed, baseline_frame=base
    )
    assert second.state == ClearanceZoneState.ABNORMAL
