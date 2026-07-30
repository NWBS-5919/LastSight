"""작업자 상태 조회 API.

TODO: app/rules/state_engine.py 의 결과를 실시간 추론 파이프라인과 연결해 반환하도록 구현.
지금은 프론트엔드(대시보드) 개발이 먼저 진행될 수 있도록 더미 데이터를 반환한다.

2026-07-30: "출구 통과 확인(evacuated)" 개념을 없애고, "화재경보 후 관측 지속 여부"만
보는 방식으로 바꿨다 (development_log.md 17-18번 참고).
"""

from fastapi import APIRouter, HTTPException

from app.models.schemas import WorkerEvent, WorkerEventLogEntry, WorkerStatus
from app.rules.worker_log import load_worker_log

router = APIRouter(prefix="/workers", tags=["workers"])

_DUMMY_CAMERA_ID = "camera-1"

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


@router.get("", response_model=list[WorkerStatus])
def list_workers() -> list[WorkerStatus]:
    return _DUMMY_WORKERS


@router.get("/{track_id}", response_model=WorkerStatus | None)
def get_worker(track_id: str) -> WorkerStatus | None:
    return next((w for w in _DUMMY_WORKERS if w.track_id == track_id), None)


@router.get("/{track_id}/timeline", response_model=list[WorkerEventLogEntry])
def get_worker_timeline(track_id: str) -> list[WorkerEventLogEntry]:
    """"10:32:15 A구역에서 관측 시작 → 10:37:20 5분 초과 체류" 같은 상태 변화 이력."""
    return load_worker_log(_DUMMY_CAMERA_ID, track_id)
