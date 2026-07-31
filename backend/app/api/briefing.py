"""구조 브리핑 카드 API.

2026-07-30: "출구 통과 확인" 개념이 없어져서, INSIDE_OBSERVED인 작업자도 카드 생성 대상에서
제외하지 않는다 — 관측이 끊긴(TRACKING_LOST) 사람뿐 아니라, 화재경보 후 계속 관측되는
(PROLONGED_PRESENCE) 사람의 위치 정보도 소방대에게 유용하기 때문. 즉 "안전이 확인된 사람만
빼고 나머지는 다 카드를 만든다"가 아니라, 요청받은 모든 작업자에 대해 카드를 만든다.

`docs/screen_guide.md` 4번 화면 원칙: 카드 상단에 "추정 정보 — 확정 아님"을 항상 노출하고,
탐지 신뢰도·시야 확보 여부를 함께 보여줘 정보가 추정치임을 드러낸다.
"""

from fastapi import APIRouter, HTTPException

from app.api.workers import _current_workers

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/{track_id}")
def get_briefing_card(track_id: str) -> dict:
    worker = next((w for w in _current_workers() if w.track_id == track_id), None)
    if worker is None:
        raise HTTPException(status_code=404, detail="해당 track_id를 찾을 수 없습니다.")

    return {
        "track_id": worker.track_id,
        "status": worker.event,
        "confidence": worker.confidence,
        "visibility": worker.visibility,
        "disclaimer": "추정 정보 — 확정 아님",
        "summary": (
            f"{worker.helmet_color or '색상 미상'} 안전모, {worker.vest_color or '색상 미상'} 안전조끼를 착용한 작업자입니다. "
            f"마지막으로 {worker.last_seen_at or '시각 미상'}에 {worker.last_zone or '구역 미상'}에서 관측되었습니다. "
            "이 정보는 추정치이며, 현재 안전 여부를 확정하지 않습니다."
        ),
        "last_frame_path": worker.last_frame_path,
        "reference_frame_path": worker.reference_frame_path,
    }
