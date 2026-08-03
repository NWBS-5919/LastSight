"""상황 타임라인 "요약 브리핑" 버튼용 API — 지금까지 기록된 데이터를 근거로 Gemini가
쓴 한국어 요약 한 건을 돌려준다(app/inference/briefing.py)."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.inference.briefing import generate_situation_summary
from app.models.schemas import SituationSummary
from app.pipeline import scenario_runner

router = APIRouter(tags=["situation-summary"])


@router.post("/situation-summary", response_model=SituationSummary)
def create_situation_summary() -> SituationSummary:
    state = scenario_runner.STATE
    now = datetime.now(UTC)
    result = generate_situation_summary(
        now=now,
        fire_alert=state.fire_alert,
        zone_person_counts=state.zone_person_counts,
        situation_checks=state.situation_checks,
        ppe_events=state.ppe_violation_events,
        current_frame_path=state.frame_image_url,
    )
    if result is None:
        raise HTTPException(status_code=502, detail="요약 브리핑을 생성하지 못했습니다. 잠시 후 다시 시도해주세요.")
    headline, points = result
    return SituationSummary(headline=headline, points=points, generated_at=now.isoformat())
