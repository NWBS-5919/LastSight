"""영상 옆 "구조 브리핑" 챗봇 API — 지금까지 기록된 데이터 + 필요하면 특정 시점 사진을
근거로 Gemini가 자유 질문에 답한다(app/inference/briefing.py)."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.inference.briefing import answer_chat_message
from app.models.schemas import ChatReply, ChatTurn
from app.pipeline import scenario_runner

router = APIRouter(tags=["situation-chat"])


@router.post("/situation-chat", response_model=ChatReply)
def create_chat_reply(messages: list[ChatTurn]) -> ChatReply:
    """messages는 지금까지의 대화 전체(마지막이 이번 사용자 질문) — 백엔드는 상태를 따로
    들고 있지 않고, 프론트엔드가 매번 전체 이력을 보낸다(단일 관리자 데모 환경이라 세션
    저장이 필요 없다)."""
    state = scenario_runner.STATE
    now = datetime.now(UTC)
    scenario_started_at = datetime.fromisoformat(state.scenario_started_at) if state.scenario_started_at else None
    result = answer_chat_message(
        messages=[m.model_dump() for m in messages],
        now=now,
        scenario_started_at=scenario_started_at,
        fire_alert=state.fire_alert,
        zone_person_counts=state.zone_person_counts,
        situation_checks=state.situation_checks,
        ppe_events=state.ppe_violation_events,
        current_frame_path=state.frame_image_url,
    )
    if result is None:
        raise HTTPException(status_code=502, detail="답변을 생성하지 못했습니다. 잠시 후 다시 시도해주세요.")
    reply, frame_path = result
    return ChatReply(reply=reply, frame_path=frame_path, generated_at=now.isoformat())
