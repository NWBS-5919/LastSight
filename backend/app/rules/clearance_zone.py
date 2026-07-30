"""평상시 예방 축 — "이 구역이 기준 화면과 달라졌는지"를 감시하는 규칙 엔진.

CLAUDE.md 6번(MVP 범위) 평상시 안전관리 항목. 소화기/전기패널/비상구 세 구역 종류 모두
판정 방식이 완전히 같다(app/rules/models.ClearanceZoneType 참고 — 소화기도 별도 탐지 모델
없이 이 방식 하나로 처리하기로 함). 종류별로 별도 알고리즘을 만들지 않는다.

원칙:
  - 사람이 구역과 겹쳐 있는 프레임은 판정에서 제외한다(순간적으로 지나가거나 그 앞에서
    작업 중인 사람을 방치물로 오인하지 않기 위함 — 기존 person 탐지 결과를 재사용).
  - 변화가 감지돼도 즉시 이상으로 확정하지 않고, 일정 시간(PERSIST_SECONDS) 이상 지속돼야
    ABNORMAL로 승격한다 (app/rules/state_engine.py의 "잠깐 스친 신호는 무시" 원칙과 동일).
    공사현장처럼 사람·자재가 빈번히 오가는 환경을 감안해 기본값을 15분으로 넉넉히 잡았다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

from app.models.schemas import ClearanceZoneDef, ClearanceZoneState, ClearanceZoneStatus
from app.rules.zone import _point_in_polygon

STATUS_DIR = Path(__file__).resolve().parents[3] / "data" / "zone_maps" / "clearance_status"
BASELINE_DIR = Path(__file__).resolve().parents[3] / "data" / "zone_maps" / "clearance_baselines"

PERSIST_SECONDS = 900  # 변화가 이 시간 이상 지속돼야 ABNORMAL로 확정 (기본 15분)
CHANGE_AREA_RATIO = 0.2  # 구역 면적의 이 비율 이상이 달라져야 "변화"로 인정 (그림자·먼지 등 미세 변화 무시)
SSIM_DIFF_THRESHOLD = 0.5  # 이 값보다 SSIM이 낮은 픽셀을 "달라진 픽셀"로 카운트


def _polygon_mask(polygon: list[tuple[float, float]], height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [pts], 1)
    return mask


def _box_overlaps_polygon(bbox_xyxy: tuple[float, float, float, float], polygon: list[tuple[float, float]]) -> bool:
    """박스의 중심점 또는 네 모서리 중 하나라도 구역 안에 있으면 겹친 것으로 본다."""
    x1, y1, x2, y2 = bbox_xyxy
    points = [((x1 + x2) / 2, (y1 + y2) / 2), (x1, y1), (x2, y1), (x1, y2), (x2, y2)]
    return any(_point_in_polygon(p, polygon) for p in points)


def _local_ssim_map(gray1: np.ndarray, gray2: np.ndarray, win: int = 7) -> np.ndarray:
    """두 그레이스케일 이미지의 지역 구조적 유사도(SSIM) 맵.

    scikit-image 의존성 없이 표준 SSIM 공식을 GaussianBlur로 지역 평균/분산을 근사해
    직접 구현했다(다른 규칙 모듈들처럼 외부 라이브러리를 최소화하는 방향). 값이 1에
    가까울수록 구조가 유사, 낮을수록 구조가 달라졌다는 뜻 — 단순 픽셀값 차이보다
    조명 변화(그림자, 밝기 변동)에 훨씬 둔감하고, 실제로 물체가 생기고 없어지는 변화에는
    민감하다."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    img1 = gray1.astype(np.float64)
    img2 = gray2.astype(np.float64)

    mu1 = cv2.GaussianBlur(img1, (win, win), 1.5)
    mu2 = cv2.GaussianBlur(img2, (win, win), 1.5)
    mu1_sq, mu2_sq, mu1_mu2 = mu1 * mu1, mu2 * mu2, mu1 * mu2

    sigma1_sq = cv2.GaussianBlur(img1 * img1, (win, win), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(img2 * img2, (win, win), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(img1 * img2, (win, win), 1.5) - mu1_mu2

    numerator = (2 * mu1_mu2 + c1) * (2 * sigma12 + c2)
    denominator = (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    return numerator / denominator


def _has_sustained_visual_change(
    zone: ClearanceZoneDef,
    current_frame: np.ndarray,
    baseline_frame: np.ndarray,
) -> bool:
    """기준 화면과 비교해, 구역 면적의 CHANGE_AREA_RATIO 이상이 구조적으로 달라졌으면 True."""
    h, w = current_frame.shape[:2]
    mask = _polygon_mask(zone.polygon, h, w)
    zone_area = float(mask.sum())
    if zone_area == 0:
        return False

    gray_current = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    gray_baseline = cv2.cvtColor(baseline_frame, cv2.COLOR_BGR2GRAY)
    ssim_map = _local_ssim_map(gray_current, gray_baseline)

    changed_pixels = float(((ssim_map < SSIM_DIFF_THRESHOLD) & (mask == 1)).sum())
    return (changed_pixels / zone_area) >= CHANGE_AREA_RATIO


def evaluate_clearance_zone(
    zone: ClearanceZoneDef,
    *,
    prev_status: ClearanceZoneStatus | None,
    now: datetime,
    current_frame: np.ndarray | None = None,
    baseline_frame: np.ndarray | None = None,
    person_boxes: list[tuple[float, float, float, float]] | None = None,
    current_frame_path: str | None = None,
) -> ClearanceZoneStatus:
    """구역 하나를 한 프레임 평가해서 새 상태를 반환한다.

    이전 상태를 인자로 받고 새 상태를 반환하는 순수 함수 스타일은
    app/rules/state_engine.py와 동일하게 맞췄다.

    사람이 구역과 겹쳐 있으면 이번 프레임 판정을 보류하고 이전 상태를 그대로 유지한다
    (지나가는 사람·구역 앞에서 작업 중인 사람을 방치물로 오인하지 않기 위함).
    """
    now_iso = now.isoformat()

    if person_boxes and any(_box_overlaps_polygon(b, zone.polygon) for b in person_boxes):
        if prev_status is None:
            return ClearanceZoneStatus(zone_id=zone.zone_id, state=ClearanceZoneState.NORMAL, last_checked_at=now_iso)
        return prev_status.model_copy(update={"last_checked_at": now_iso})

    if current_frame is None or baseline_frame is None:
        return ClearanceZoneStatus(zone_id=zone.zone_id, state=ClearanceZoneState.CAMERA_FAILURE, last_checked_at=now_iso)
    changed = _has_sustained_visual_change(zone, current_frame, baseline_frame)

    if not changed:
        return ClearanceZoneStatus(
            zone_id=zone.zone_id,
            state=ClearanceZoneState.NORMAL,
            changed_since=None,
            last_checked_at=now_iso,
            last_frame_path=current_frame_path,
        )

    changed_since = prev_status.changed_since if (prev_status and prev_status.changed_since) else now_iso
    duration = now - datetime.fromisoformat(changed_since)
    state = (
        ClearanceZoneState.ABNORMAL if duration >= timedelta(seconds=PERSIST_SECONDS) else ClearanceZoneState.OBSERVING
    )

    return ClearanceZoneStatus(
        zone_id=zone.zone_id,
        state=state,
        changed_since=changed_since,
        last_checked_at=now_iso,
        last_frame_path=current_frame_path,
    )


# ---- 상태 영속화 (zone.py의 load_zone_map/save_zone_map과 같은 패턴) ----


def _status_path(camera_id: str) -> Path:
    return STATUS_DIR / f"{camera_id}.json"


def load_clearance_statuses(camera_id: str) -> dict[str, ClearanceZoneStatus]:
    path = _status_path(camera_id)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {zone_id: ClearanceZoneStatus.model_validate(v) for zone_id, v in raw.items()}


def save_clearance_status(camera_id: str, status: ClearanceZoneStatus) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    statuses = load_clearance_statuses(camera_id)
    statuses[status.zone_id] = status
    path = _status_path(camera_id)
    path.write_text(
        json.dumps({zid: s.model_dump() for zid, s in statuses.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def baseline_image_path(camera_id: str, zone_id: str) -> Path:
    return BASELINE_DIR / camera_id / f"{zone_id}.jpg"
