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
    first_seen_at: str | None = None,
    camera_ok: bool = True,
    last_zone: str | None = None,
    last_seen_at: str | None = None,
    last_frame_path: str | None = None,
    reference_frame_path: str | None = None,
    prolonged_presence_minutes: float = PROLONGED_PRESENCE_MINUTES,
) -> WorkerStatus:
    """현재 관측 상태 + "이 작업자가" 얼마나 오래 관측되고 있는지로 상태를 결정한다.

    - camera_ok=False → CAMERA_FAILURE (사람 상태와 무관하게 카메라 자체 문제 우선 표시)
    - is_currently_observed=False → TRACKING_LOST (안전 여부를 추측하지 않고 사실만 전달)
    - is_currently_observed=True, first_seen_at(이 track_id가 처음 감지된 시각)부터
      prolonged_presence_minutes 초과 → PROLONGED_PRESENCE
    - 그 외(관측 중이며 아직 임계시간 이내, 또는 화재 자체가 없음) → INSIDE_OBSERVED

    2026-08-03 정정: 원래 "화재경보 발생 시각부터" 경과 시간을 쟀는데, 이러면 화재 발생
    한참 뒤에야 처음 나타난 사람도(자기 관측 지속시간은 짧아도) 화재 자체가 오래전에
    터졌다는 이유만으로 즉시 PROLONGED_PRESENCE가 돼버렸다 — "이 사람이 얼마나 오래
    관측되고 있는지" 본다는 원래 취지(이 모듈 docstring)와 어긋났고, 대시보드에 보여주는
    "체류 시간"(작업자별 첫 감지~마지막 확인)과도 서로 다른 기준이라 혼란스러웠다(실측 —
    막 나타난 사람이 곧바로 장기체류경고로 표시됨). first_seen_at 기준으로 바꿔 두 값을
    일치시켰다.

    prolonged_presence_minutes 기본값은 모듈 상수(PROLONGED_PRESENCE_MINUTES, 5분)를 그대로
    쓴다 — 데모 시나리오처럼 짧은 재생 시간 안에 상태 전환을 보여줘야 할 때만 호출부에서
    더 작은 값을 넘겨 쓴다(실제 운영 기본값 자체를 바꾸는 게 아니라 호출부 재량).
    """
    if not camera_ok:
        event = WorkerEvent.CAMERA_FAILURE
    elif not is_currently_observed:
        event = WorkerEvent.TRACKING_LOST
    elif (
        fire_triggered_at is not None
        and first_seen_at is not None
        and (now - datetime.fromisoformat(first_seen_at)) >= timedelta(minutes=prolonged_presence_minutes)
    ):
        event = WorkerEvent.PROLONGED_PRESENCE
    else:
        event = WorkerEvent.INSIDE_OBSERVED

    return WorkerStatus(
        track_id=track_id,
        event=event,
        first_seen_at=first_seen_at,
        last_zone=last_zone,
        last_seen_at=last_seen_at,
        last_frame_path=last_frame_path,
        reference_frame_path=reference_frame_path,
    )
