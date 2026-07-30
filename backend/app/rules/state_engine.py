"""작업자 상태 규칙 엔진.

2026-07-30 재설계: "출구를 통과했는지" 판정 대신, 화재경보 발생 이후
"지금도 관측되고 있는가·얼마나 오래 관측되고 있는가"만 본다 (development_log.md 17-18번 참고).
CCTV가 문 바깥쪽까지 잡는 경우가 현실적으로 드물어 "통과 확인" 자체가 구조적으로 어려웠고,
설령 통과를 확인해도 "대피 완료를 AI가 확정 선언한다"는 것 자체가 CLAUDE.md 절대 원칙과
긴장 관계였다. 이 방식은 그 긴장을 근본적으로 없앤다 — 이 시스템은 누구도 "안전하다"고
선언하지 않고, "관측되는지·언제부터 관측 안 되는지"만 정직하게 보고한다.
"""

from datetime import datetime, timedelta

from app.models.schemas import WorkerEvent, WorkerStatus

PROLONGED_PRESENCE_MINUTES = 5  # 화재경보 후 이 시간 넘도록 계속 관측되면 PROLONGED_PRESENCE로 승격


def resolve_status(
    track_id: str,
    *,
    is_currently_observed: bool,
    now: datetime,
    fire_triggered_at: datetime | None = None,
    camera_ok: bool = True,
    last_zone: str | None = None,
    last_seen_at: str | None = None,
    last_frame_path: str | None = None,
    reference_frame_path: str | None = None,
) -> WorkerStatus:
    """현재 관측 상태 + 화재경보 이후 경과 시간으로 상태를 결정한다.

    - camera_ok=False → CAMERA_FAILURE (사람 상태와 무관하게 카메라 자체 문제 우선 표시)
    - is_currently_observed=False → TRACKING_LOST (안전 여부를 추측하지 않고 사실만 전달)
    - is_currently_observed=True, 화재경보 후 PROLONGED_PRESENCE_MINUTES 초과 → PROLONGED_PRESENCE
    - 그 외(관측 중이며 아직 임계시간 이내, 또는 화재 자체가 없음) → INSIDE_OBSERVED
    """
    if not camera_ok:
        event = WorkerEvent.CAMERA_FAILURE
    elif not is_currently_observed:
        event = WorkerEvent.TRACKING_LOST
    elif fire_triggered_at is not None and (now - fire_triggered_at) >= timedelta(minutes=PROLONGED_PRESENCE_MINUTES):
        event = WorkerEvent.PROLONGED_PRESENCE
    else:
        event = WorkerEvent.INSIDE_OBSERVED

    return WorkerStatus(
        track_id=track_id,
        event=event,
        last_zone=last_zone,
        last_seen_at=last_seen_at,
        last_frame_path=last_frame_path,
        reference_frame_path=reference_frame_path,
    )
