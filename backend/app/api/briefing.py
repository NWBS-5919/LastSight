"""구조 브리핑 카드 API.

TODO: app/briefing 의 참조 프레임 선택 로직과 연결해 실제 카드를 생성하도록 구현.

2026-07-30: "출구 통과 확인" 개념이 없어져서, INSIDE_OBSERVED인 작업자도 카드 생성 대상에서
제외하지 않는다 — 관측이 끊긴(TRACKING_LOST) 사람뿐 아니라, 화재경보 후 계속 관측되는
(PROLONGED_PRESENCE) 사람의 위치 정보도 소방대에게 유용하기 때문. 즉 "안전이 확인된 사람만
빼고 나머지는 다 카드를 만든다"가 아니라, 요청받은 모든 작업자에 대해 카드를 만든다.
"""

from fastapi import APIRouter, HTTPException

from app.api.workers import _DUMMY_WORKERS

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/{track_id}")
def get_briefing_card(track_id: str) -> dict:
    worker = next((w for w in _DUMMY_WORKERS if w.track_id == track_id), None)
    if worker is None:
        raise HTTPException(status_code=404, detail="해당 track_id를 찾을 수 없습니다.")

    return {
        "track_id": worker.track_id,
        "status": worker.event,
        "summary": (
            f"{worker.helmet_color or '색상 미상'} 안전모, {worker.vest_color or '색상 미상'} 안전조끼를 착용한 작업자입니다. "
            f"마지막으로 {worker.last_seen_at or '시각 미상'}에 {worker.last_zone or '구역 미상'}에서 관측되었습니다. "
            "이 정보는 추정치이며, 현재 안전 여부를 확정하지 않습니다."
        ),
        "last_frame_path": worker.last_frame_path,
        "reference_frame_path": worker.reference_frame_path,
    }
