"""평상시 안전 대시보드(화면1)용 PPE/화재경보 요약 API.

`docs/screen_guide.md` 1번·3번 화면이 요구하는 집계 엔드포인트 — 시나리오 러너의
in-memory 상태를 그대로 집계해서 반환한다.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import PpeViolationLogEntry, WorkerEvent
from app.pipeline import scenario_runner
from app.rules.ppe_violation_log import LOG_DIR as PPE_VIOLATION_LOG_DIR
from app.rules.ppe_violation_log import load_ppe_violation_log

router = APIRouter(tags=["ppe"])


def _violation_track_ids(camera_id: str) -> list[str]:
    d = PPE_VIOLATION_LOG_DIR / camera_id
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


@router.get("/ppe/summary")
def ppe_summary() -> dict:
    return {
        "violations_today": scenario_runner.STATE.ppe_violations_today,
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
    붙어있어, 관리자가 클릭하면 그 순간의 증거 사진을 볼 수 있다 — 추적 ID가 중간에 바뀌어도
    로그는 끊기지 않고 계속 쌓인다(같은 사람인지는 사진을 보고 관리자가 직접 판단)."""
    rows: list[PpeViolationLogEntry] = []
    for track_id in _violation_track_ids(camera_id):
        rows.extend(load_ppe_violation_log(camera_id, track_id))
    return sorted(rows, key=lambda e: e.at)
