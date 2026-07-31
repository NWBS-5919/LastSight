"""화재경보 자동 트리거.

app.inference.fire_detector 의 탐지 결과가 일정 프레임 이상 연속으로 임계값을 넘으면
FireAlert(source=AUTO_DETECTION)를 발생시킨다. 관리자가 수동으로 발생시키는 경로도
그대로 유지한다(source=MANUAL) — 자동 탐지를 놓치는 경우의 안전망.
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
    min_hit_ratio: float = 0.6,
    min_window_size: int = 5,
) -> FireAlert | None:
    """최근 N프레임의 fire/smoke 탐지 이력을 보고 경보를 발생시킬지 판정.

    단발성 오탐으로 경보가 울리지 않도록, 최근 프레임의 `min_hit_ratio` 이상에서
    confidence_threshold를 넘는 탐지가 있어야 트리거한다 (기본: 최근 프레임의 60% 이상).
    이 값들은 임의 기본값이므로 실제 데이터로 튜닝하고 experiments/logs/에 기록할 것 —
    너무 낮으면 오탐(false alarm), 너무 높으면 놓침(False All-Clear 위험)으로 이어진다.

    `min_window_size`: recent_detections가 아직 이 개수만큼 안 쌓였으면(카메라가 막
    켜졌거나 화재경보 판정을 막 시작한 시점) 트리거하지 않는다. 이게 없으면 프레임
    1~2개짜리 작은 표본에서 우연히 오탐 1건만 있어도 비율이 100%가 되어 바로 경보가
    울리는 결함이 있었다(development_log.md 참고, 데모 시나리오에서 실측으로 발견).
    """
    if len(recent_detections) < min_window_size:
        return None

    hits = sum(
        1 for frame_detections in recent_detections if any(d.confidence >= confidence_threshold for d in frame_detections)
    )
    if hits / len(recent_detections) < min_hit_ratio:
        return None

    return FireAlert(
        camera_id=camera_id,
        zone_id=zone_id,
        triggered_at=datetime.now(UTC).isoformat(),
        source=AlarmSource.AUTO_DETECTION,
        confidence=max(
            (d.confidence for frame_detections in recent_detections for d in frame_detections),
            default=None,
        ),
    )


def manual_trigger(camera_id: str, zone_id: str | None, triggered_at: str) -> FireAlert:
    return FireAlert(camera_id=camera_id, zone_id=zone_id, triggered_at=triggered_at, source=AlarmSource.MANUAL)
