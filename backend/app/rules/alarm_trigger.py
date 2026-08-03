"""화재경보 자동 트리거.

app.inference.fire_detector 의 탐지 결과를 **5초 주기로 샘플링**하면서(호출 측 책임 —
실 서비스는 이 간격으로 fire_detector.detect()를 불러 recent_detections에 쌓을 것),
최근 샘플이 `consecutive_required`번 연속으로 임계값을 넘으면 FireAlert(source=AUTO_DETECTION)를
발생시킨다. 관리자가 수동으로 발생시키는 경로도 그대로 유지한다(source=MANUAL) — 자동
탐지를 놓치는 경우의 안전망.

2026-08-02: 기존엔 "최근 5프레임 중 60% 이상 양성"이라는 윈도우+비율 규칙을 썼는데,
5초 주기로 샘플링하는 전제라면 "최근 2개 샘플이 연속으로 양성"(=10초 확인)이라는 더 단순한
규칙으로 충분하다고 판단해 교체했다 — 단발 오탐은 여전히 1개만으로는 안 걸리게 막고, 그 이상
복잡한 비율 계산은 안 하는 쪽으로 단순화.
"""

from datetime import UTC, datetime

from app.inference.fire_detector import FireDetection
from app.models.schemas import AlarmSource, FireAlert


def evaluate(
    camera_id: str,
    recent_detections: list[list[FireDetection]],
    *,
    zone_id: str | None = None,
    confidence_threshold: float = 0.6,
    consecutive_required: int = 2,
) -> FireAlert | None:
    """최근 샘플들을 보고 경보를 발생시킬지 판정.

    recent_detections의 **마지막 consecutive_required개**가 전부 "양성"(confidence_threshold
    이상인 탐지가 최소 1개 있음)이어야 트리거한다. 표본이 consecutive_required개보다 적으면
    아직 판단하지 않는다(단발성 오탐 방지 — 1개 샘플만으로는 절대 안 울림).
    """
    if len(recent_detections) < consecutive_required:
        return None

    last_n = recent_detections[-consecutive_required:]
    all_positive = all(any(d.confidence >= confidence_threshold for d in frame_detections) for frame_detections in last_n)
    if not all_positive:
        return None

    return FireAlert(
        camera_id=camera_id,
        zone_id=zone_id,
        triggered_at=datetime.now(UTC).isoformat(),
        source=AlarmSource.AUTO_DETECTION,
        confidence=max((d.confidence for frame_detections in last_n for d in frame_detections), default=None),
    )


def manual_trigger(camera_id: str, zone_id: str | None, triggered_at: str) -> FireAlert:
    return FireAlert(camera_id=camera_id, zone_id=zone_id, triggered_at=triggered_at, source=AlarmSource.MANUAL)
