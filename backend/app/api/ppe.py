"""평상시 안전 대시보드(화면1)용 PPE/화재경보 요약 API.

`docs/screen_guide.md` 1번·3번 화면이 요구하는 집계 엔드포인트 — 시나리오 러너의
in-memory 상태를 그대로 집계해서 반환한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.schemas import PpeDetectionSettings, PpeViolationLogEntry, WorkerEvent, ZoneSituationLogEntry
from app.pipeline import scenario_runner
from app.rules import ppe_settings
from app.rules.ppe_violation_log import load_ppe_violation_log, merge_violations, update_violation_review
from app.rules.zone_situation_log import load_zone_situation_log

router = APIRouter(tags=["ppe"])


@router.get("/ppe-settings/{camera_id}", response_model=PpeDetectionSettings)
def get_ppe_settings(camera_id: str) -> PpeDetectionSettings:
    """카메라별 헬멧/조끼 감지 on/off 설정을 조회. 저장된 값이 없으면 둘 다 켜진 기본값."""
    return ppe_settings.load_ppe_settings(camera_id)


@router.put("/ppe-settings/{camera_id}", response_model=PpeDetectionSettings)
def put_ppe_settings(camera_id: str, settings: PpeDetectionSettings) -> PpeDetectionSettings:
    """헬멧/조끼 감지를 각각 켜고 끈다. 다음 프레임부터 바로 반영된다(scenario_runner가
    매 프레임 이 설정을 다시 읽는다)."""
    settings.camera_id = camera_id
    ppe_settings.save_ppe_settings(settings)
    return settings


@router.get("/ppe/summary")
def ppe_summary() -> dict:
    return {
        "violations_today": len(scenario_runner.STATE.ppe_violation_events),
        "zone_person_counts": scenario_runner.STATE.zone_person_counts,
        "camera_ok": True,
        "event_feed": scenario_runner.STATE.event_feed[-10:],
    }


@router.get("/workers/summary")
def workers_summary() -> dict:
    counts = {e.value: 0 for e in WorkerEvent}
    for w in scenario_runner.STATE.workers.values():
        counts[w.event.value] += 1
    return {
        "total": len(scenario_runner.STATE.workers),
        **counts,
    }


@router.get("/fire-alerts/latest")
def latest_fire_alert() -> dict | None:
    alert = scenario_runner.STATE.fire_alert
    return alert.model_dump() if alert else None


@router.get("/ppe-violations/{camera_id}", response_model=list[PpeViolationLogEntry])
def list_ppe_violations(camera_id: str) -> list[PpeViolationLogEntry]:
    """PPE 미착용이 새로 감지된 순간들을 시간순으로 반환. 각 항목에 frame_path/bbox_xyxy가
    붙어있어, 관리자가 클릭하면 그 순간의 증거 사진을 볼 수 있다. 평상시엔 추적 자체를
    안 하므로 track_id는 없고, 위치+시간 기반으로 "같은 위반이 계속되는 중인지"만 구분한다
    (app/rules/ppe_violation_log.py)."""
    return sorted(load_ppe_violation_log(camera_id), key=lambda e: e.at)


class PpeViolationReview(BaseModel):
    helmet: str | None = None  # "worn"/"not_worn" — None이면 그 항목은 그대로 둔다는 뜻이 아니라 명시적으로 제출할 것
    vest: str | None = None


@router.patch("/ppe-violations/{camera_id}/{entry_id}", response_model=PpeViolationLogEntry)
async def review_ppe_violation(camera_id: str, entry_id: str, review: PpeViolationReview) -> PpeViolationLogEntry:
    """관리자가 카드에서 안전모/안전조끼 최종 판정을 확정 제출한다 — AI 원판정은 지우지
    않고 reviewed_* 필드에 별도로 남긴다. 둘 다 "착용"으로 정정해도 이 항목 자체는 로그에서
    지워지지 않는다(오탐이었다는 사실 자체가 감사 기록으로 남아야 하므로) — 대신 카드 UI가
    "정정됨(오탐)"으로 표시한다."""
    updated = update_violation_review(
        camera_id,
        entry_id,
        reviewed_helmet=review.helmet,
        reviewed_vest=review.vest,
        reviewed_at=datetime.now(UTC).isoformat(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="해당 위반 기록을 찾을 수 없습니다.")

    # 라이브 상태(현재 연결된 대시보드들)에도 반영 — 이 목록에서 같은 id를 찾아 교체한다.
    for i, e in enumerate(scenario_runner.STATE.ppe_violation_events):
        if e.id == entry_id:
            scenario_runner.STATE.ppe_violation_events[i] = updated
            break
    await scenario_runner._broadcast()

    return updated


class PpeViolationMerge(BaseModel):
    id_a: str
    id_b: str


@router.post("/ppe-violations/{camera_id}/merge", response_model=PpeViolationLogEntry)
async def merge_ppe_violations(camera_id: str, merge: PpeViolationMerge) -> PpeViolationLogEntry:
    """관리자가 타임라인에서 노드 하나를 다른 노드 위로 끌어다 놓아 "사실은 같은 위반이
    두 줄로 쪼개진 것"이라고 확정한다(위치 매칭 실패로 인한 중복, development_log.md 참고).
    시각이 이른 쪽을 남기고(카드에 가장 처음 감지된 이미지가 보이도록) 나머지는 로그에서
    제거한다."""
    merged = merge_violations(camera_id, merge.id_a, merge.id_b)
    if merged is None:
        raise HTTPException(status_code=404, detail="병합할 위반 기록을 찾을 수 없습니다.")

    events = scenario_runner.STATE.ppe_violation_events
    events[:] = [e for e in events if e.id not in (merge.id_a, merge.id_b)]
    events.append(merged)
    events.sort(key=lambda e: e.at)
    await scenario_runner._broadcast()

    return merged


@router.get("/zone-situation/{camera_id}", response_model=list[ZoneSituationLogEntry])
def list_zone_situation(camera_id: str) -> list[ZoneSituationLogEntry]:
    """화재 발생 후 장기체류 전환마다 남긴 구역별 상황 집계 로그를 시간순으로 반환."""
    return sorted(load_zone_situation_log(camera_id), key=lambda e: e.at)
