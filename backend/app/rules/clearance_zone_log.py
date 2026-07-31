"""관리구역 상태 변화 타임라인 저장·조회 (app/rules/worker_log.py와 같은 파일 기반 영속화 패턴).

매 프레임 기록하지 않고, evaluate_clearance_zone()이 계산한 새 상태가 직전과 다를 때만
한 줄 남긴다 (예: "10:32:15 소화기A 변화 감지 시작", "10:47:20 소화기A 이상 확정").
"""

import json
from pathlib import Path

from app.models.schemas import ClearanceZoneLogEntry, ClearanceZoneStatus

LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "clearance_zone_logs"


def _log_path(camera_id: str, zone_id: str) -> Path:
    return LOG_DIR / camera_id / f"{zone_id}.json"


def load_clearance_zone_log(camera_id: str, zone_id: str) -> list[ClearanceZoneLogEntry]:
    path = _log_path(camera_id, zone_id)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ClearanceZoneLogEntry.model_validate(v) for v in raw]


def _append(camera_id: str, entry: ClearanceZoneLogEntry) -> None:
    path = _log_path(camera_id, entry.zone_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    log = load_clearance_zone_log(camera_id, entry.zone_id)
    log.append(entry)
    path.write_text(json.dumps([e.model_dump() for e in log], ensure_ascii=False, indent=2), encoding="utf-8")


def record_if_changed(
    camera_id: str, prev_status: ClearanceZoneStatus | None, new_status: ClearanceZoneStatus, now_iso: str
) -> None:
    """직전 상태와 state가 달라졌을 때만 로그 한 줄을 남긴다."""
    if prev_status is not None and prev_status.state == new_status.state:
        return
    _append(
        camera_id,
        ClearanceZoneLogEntry(
            zone_id=new_status.zone_id,
            state=new_status.state,
            at=now_iso,
            situation_note=new_status.situation_note,
        ),
    )
