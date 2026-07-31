"""사고 리플레이 — 화재경보/작업자 상태변화/관리구역 상태변화 로그를 시간순으로 합쳐서
"그 시각에 무슨 일이 있었는지" 다시 볼 수 있게 한다.

fire_alert_log/worker_log/clearance_zone_log는 전부 이미 상태가 바뀔 때만 append-only로
기록되고 있었다 — 이 API는 그 로그들을 새로 만드는 게 아니라 병합·재구성만 한다.
사고 이후 감사·훈련·보고 자료로 그대로 쓸 수 있는 것이 목적이다.
"""

from datetime import datetime

from fastapi import APIRouter

from app.models.schemas import (
    ClearanceZoneLogEntry,
    FireAlert,
    IncidentTimelineEntry,
    PpeViolationLogEntry,
    WorkerEventLogEntry,
)
from app.rules.clearance_zone_log import LOG_DIR as CLEARANCE_LOG_DIR
from app.rules.clearance_zone_log import load_clearance_zone_log
from app.rules.fire_alert_log import load_fire_alerts
from app.rules.ppe_violation_log import LOG_DIR as PPE_VIOLATION_LOG_DIR
from app.rules.ppe_violation_log import load_ppe_violation_log
from app.rules.worker_log import LOG_DIR as WORKER_LOG_DIR
from app.rules.worker_log import load_worker_log

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _track_ids(camera_id: str) -> list[str]:
    d = WORKER_LOG_DIR / camera_id
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _clearance_zone_ids(camera_id: str) -> list[str]:
    d = CLEARANCE_LOG_DIR / camera_id
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _ppe_violation_track_ids(camera_id: str) -> list[str]:
    d = PPE_VIOLATION_LOG_DIR / camera_id
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _fire_alert_entry(alert: FireAlert) -> IncidentTimelineEntry:
    conf_str = f"{alert.confidence:.2f}" if alert.confidence is not None else "N/A"
    return IncidentTimelineEntry(
        at=alert.triggered_at,
        source="fire_alert",
        text=f"🔥 화재경보 발생 (신뢰도 {conf_str})" + (f" — {alert.zone_id}" if alert.zone_id else ""),
        zone_id=alert.zone_id,
    )


def _worker_entry(camera_id: str, entry: WorkerEventLogEntry) -> IncidentTimelineEntry:
    zone_str = f" ({entry.zone})" if entry.zone else ""
    return IncidentTimelineEntry(
        at=entry.at,
        source="worker",
        text=f"{entry.track_id} 상태 변화: {entry.event.value}{zone_str}",
        track_id=entry.track_id,
        zone_id=entry.zone,
        situation_note=entry.situation_note,
        frame_path=entry.frame_path,
        bbox_xyxy=entry.bbox_xyxy,
    )


def _clearance_entry(entry: ClearanceZoneLogEntry) -> IncidentTimelineEntry:
    return IncidentTimelineEntry(
        at=entry.at,
        source="clearance_zone",
        text=f"관리구역 {entry.zone_id} 상태 변화: {entry.state.value}",
        zone_id=entry.zone_id,
        situation_note=entry.situation_note,
    )


def _ppe_violation_entry(entry: PpeViolationLogEntry) -> IncidentTimelineEntry:
    zone_str = f" ({entry.zone})" if entry.zone else ""
    return IncidentTimelineEntry(
        at=entry.at,
        source="ppe_violation",
        text=f"{entry.track_id} {entry.violation} 미착용 감지{zone_str}",
        track_id=entry.track_id,
        zone_id=entry.zone,
        frame_path=entry.frame_path,
        bbox_xyxy=entry.bbox_xyxy,
    )


def _build_timeline(camera_id: str) -> list[IncidentTimelineEntry]:
    rows: list[IncidentTimelineEntry] = []
    for alert in load_fire_alerts(camera_id):
        rows.append(_fire_alert_entry(alert))
    for track_id in _track_ids(camera_id):
        for entry in load_worker_log(camera_id, track_id):
            rows.append(_worker_entry(camera_id, entry))
    for zone_id in _clearance_zone_ids(camera_id):
        for entry in load_clearance_zone_log(camera_id, zone_id):
            rows.append(_clearance_entry(entry))
    for track_id in _ppe_violation_track_ids(camera_id):
        for entry in load_ppe_violation_log(camera_id, track_id):
            rows.append(_ppe_violation_entry(entry))
    return sorted(rows, key=lambda r: r.at)


@router.get("/{camera_id}/timeline", response_model=list[IncidentTimelineEntry])
def get_timeline(camera_id: str) -> list[IncidentTimelineEntry]:
    """화재경보 발생부터 지금까지의 전체 사고 기록을 시간순으로 반환 (사고 리플레이용)."""
    return _build_timeline(camera_id)


@router.get("/{camera_id}/state-at", response_model=dict)
def get_state_at(camera_id: str, at: str) -> dict:
    """주어진 시각(ISO8601) 기준으로 "그때 무엇이 사실이었는지" 재구성한다.

    각 작업자/관리구역마다 그 시각 이전(포함)의 가장 최근 로그 항목을 찾아 상태를 복원한다.
    로그가 하나도 없으면(그 시각에 아직 등장하지 않았으면) 결과에서 제외한다.
    """
    cutoff = datetime.fromisoformat(at)

    fire_alert_at_time: FireAlert | None = None
    for alert in load_fire_alerts(camera_id):
        if datetime.fromisoformat(alert.triggered_at) <= cutoff:
            if fire_alert_at_time is None or alert.triggered_at > fire_alert_at_time.triggered_at:
                fire_alert_at_time = alert

    workers_at_time: dict[str, WorkerEventLogEntry] = {}
    for track_id in _track_ids(camera_id):
        candidates = [e for e in load_worker_log(camera_id, track_id) if datetime.fromisoformat(e.at) <= cutoff]
        if candidates:
            workers_at_time[track_id] = max(candidates, key=lambda e: e.at)

    zones_at_time: dict[str, ClearanceZoneLogEntry] = {}
    for zone_id in _clearance_zone_ids(camera_id):
        candidates = [e for e in load_clearance_zone_log(camera_id, zone_id) if datetime.fromisoformat(e.at) <= cutoff]
        if candidates:
            zones_at_time[zone_id] = max(candidates, key=lambda e: e.at)

    return {
        "at": at,
        "fire_alert": fire_alert_at_time.model_dump() if fire_alert_at_time else None,
        "workers": {tid: e.model_dump() for tid, e in workers_at_time.items()},
        "clearance_zones": {zid: e.model_dump() for zid, e in zones_at_time.items()},
    }
