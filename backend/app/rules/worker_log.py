"""작업자별 상태 변화 타임라인 저장·조회 (app/rules/zone.py와 같은 파일 기반 영속화 패턴).

매 프레임 기록하지 않고, resolve_status()가 계산한 새 상태가 직전과 다를 때만 한 줄 남긴다
(예: "10:32:15 Room2에서 관측 시작", "10:37:20 Room2에서 5분 초과 체류 확인").
"""

import json
from pathlib import Path

from app.models.schemas import WorkerEventLogEntry, WorkerStatus

LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "worker_logs"


def _log_path(camera_id: str, track_id: str) -> Path:
    return LOG_DIR / camera_id / f"{track_id}.json"


def load_worker_log(camera_id: str, track_id: str) -> list[WorkerEventLogEntry]:
    path = _log_path(camera_id, track_id)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [WorkerEventLogEntry.model_validate(v) for v in raw]


def _append(camera_id: str, entry: WorkerEventLogEntry) -> None:
    path = _log_path(camera_id, entry.track_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    log = load_worker_log(camera_id, entry.track_id)
    log.append(entry)
    path.write_text(json.dumps([e.model_dump() for e in log], ensure_ascii=False, indent=2), encoding="utf-8")


def record_if_changed(
    camera_id: str,
    prev_status: WorkerStatus | None,
    new_status: WorkerStatus,
    now_iso: str,
    *,
    bbox_xyxy: tuple[float, float, float, float] | None = None,
) -> None:
    """직전 상태와 event가 달라졌을 때만 로그 한 줄을 남긴다.

    frame_path는 new_status.last_frame_path를 그대로 쓴다 — 관리자가 로그를 클릭했을 때
    그 순간의 증거 사진을 볼 수 있게 하기 위함(추적 ID가 바뀌어도 사진은 항상 남는다)."""
    if prev_status is not None and prev_status.event == new_status.event:
        return
    _append(
        camera_id,
        WorkerEventLogEntry(
            track_id=new_status.track_id,
            event=new_status.event,
            zone=new_status.last_zone,
            at=now_iso,
            frame_path=new_status.last_frame_path,
            bbox_xyxy=bbox_xyxy,
        ),
    )


def update_last_situation_note(camera_id: str, track_id: str, situation_note: str) -> None:
    """가장 최근 로그 항목에 situation_note를 채워넣는다. ZERO 2차 확인(app.inference.situation_probe)이
    상태 전환 로그를 남긴 뒤 비동기로 완료되기 때문에, 로그를 쓸 때는 아직 결과가 없어
    나중에 도착한 결과를 마지막 항목에 덧붙이는 방식으로 처리한다."""
    path = _log_path(camera_id, track_id)
    log = load_worker_log(camera_id, track_id)
    if not log:
        return
    log[-1].situation_note = situation_note
    path.write_text(json.dumps([e.model_dump() for e in log], ensure_ascii=False, indent=2), encoding="utf-8")
