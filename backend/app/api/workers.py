"""작업자 상태 조회 API.

`app.pipeline.scenario_runner`가 데모 시나리오를 재생하는 동안 채우는 in-memory 상태를
반환한다. 시나리오를 아직 시작하지 않았으면(빈 상태) 프론트엔드 개발/미리보기용
더미 데이터로 대체한다 — `POST /scenario/start` 이후에는 항상 실제 상태가 우선한다.

2026-07-30: "출구 통과 확인(evacuated)" 개념을 없애고, "화재경보 후 관측 지속 여부"만
보는 방식으로 바꿨다 (development_log.md 17-18번 참고).
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.models.schemas import WorkerEvent, WorkerEventLogEntry, WorkerStatus
from app.pipeline import scenario_runner
from app.pipeline.scenario_runner import DEMO_CAMERA_ID
from app.rules.fire_alert_log import latest_fire_alert
from app.rules.triage import rank_workers
from app.rules.worker_log import load_worker_log
from app.rules.zone import load_zone_map

router = APIRouter(prefix="/workers", tags=["workers"])

_DUMMY_WORKERS = [
    WorkerStatus(track_id="P01", event=WorkerEvent.INSIDE_OBSERVED, last_zone="A구역"),
    WorkerStatus(track_id="P02", event=WorkerEvent.TRACKING_LOST, last_zone="출구1 인근", last_seen_at="2026-07-30T14:02:40"),
    WorkerStatus(
        track_id="P03",
        event=WorkerEvent.PROLONGED_PRESENCE,
        last_zone="B구역",
        last_seen_at="2026-07-30T14:08:10",
    ),
    WorkerStatus(
        track_id="P04",
        event=WorkerEvent.PROLONGED_PRESENCE,
        last_zone="C구역 창고 입구",
        last_seen_at="2026-07-30T14:09:02",
    ),
]


def _current_workers() -> list[WorkerStatus]:
    return list(scenario_runner.STATE.workers.values()) or _DUMMY_WORKERS


@router.get("", response_model=list[WorkerStatus])
def list_workers() -> list[WorkerStatus]:
    return _current_workers()


@router.get("/{track_id}", response_model=WorkerStatus | None)
def get_worker(track_id: str) -> WorkerStatus | None:
    return next((w for w in _current_workers() if w.track_id == track_id), None)


@router.get("/{track_id}/timeline", response_model=list[WorkerEventLogEntry])
def get_worker_timeline(track_id: str) -> list[WorkerEventLogEntry]:
    """"10:32:15 A구역에서 관측 시작 → 10:37:20 5분 초과 체류" 같은 상태 변화 이력."""
    camera_id = DEMO_CAMERA_ID if scenario_runner.STATE.workers else "camera-1"
    return load_worker_log(camera_id, track_id)


@router.get("/priority/ranked")
def get_priority_ranking() -> list[dict]:
    """확인이 필요한(장기체류경고/관측안됨) 작업자만 우선순위 점수 내림차순으로 반환.

    "누구부터 확인해야 하는지"에 대한 참고용 순위일 뿐, 위험도 확정이 아니다 — 지속시간·
    화재구역과의 거리·탐지 신뢰도 3가지 구성요소를 그대로 노출해 왜 이 순서인지 확인할 수
    있게 한다 (app/rules/triage.py).
    """
    camera_id = DEMO_CAMERA_ID if scenario_runner.STATE.workers else "camera-1"
    alert = latest_fire_alert(camera_id)
    zone_map = load_zone_map(camera_id)
    ranked = rank_workers(
        _current_workers(),
        now=datetime.now(UTC),
        fire_zone_id=alert.zone_id if alert else None,
        zone_map=zone_map,
        log_loader=load_worker_log,
        camera_id=camera_id,
    )
    return [b.__dict__ for b in ranked]
