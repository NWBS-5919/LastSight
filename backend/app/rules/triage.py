"""확인 우선순위 스코어 — 화재경보 후 미확인 인원이 여럿일 때 "누구부터 확인할지" 순위.

정확한 재실 인원 확정이나 위험도 판정이 아니라(CLAUDE.md 2번 절대 원칙과 충돌하지 않도록),
"어느 확인 대상을 먼저 살펴볼지"에 대한 참고용 순위일 뿐이다 — 점수가 낮다고 안전하다는
뜻도, 높다고 위험 확정이라는 뜻도 아니다. 응급실 트리아지처럼 한정된 확인 인력을 어디부터
투입할지 돕는 목적으로, 세 가지 요소를 explainable하게(각 구성요소를 그대로 노출) 합산한다:

  1. 지속시간 — 지금 상태(PROLONGED_PRESENCE/TRACKING_LOST)가 얼마나 오래 지속됐는지
     (worker_log에서 이 상태로 바뀐 시각을 찾아 계산). 오래될수록 확인 필요성이 큼.
  2. 화재 발생 구역과의 거리 — 구역 중심점 간 유클리드 거리. 가까울수록 확인 필요성이 큼.
  3. 탐지 신뢰도 — 마지막 관측이 얼마나 확실했는지. 낮은 신뢰도는 약하게만 감점한다
     (신뢰도가 낮다고 그 신호를 아예 무시하면, 애매하지만 진짜 위험한 신호를 놓칠 수 있음).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from app.models.schemas import WorkerEvent, WorkerEventLogEntry, WorkerStatus, ZoneMapConfig

_DURATION_CAP_MINUTES = 30.0  # 이 이상 지속되면 지속시간 점수는 만점으로 포화
_DURATION_WEIGHT = 50.0
_PROXIMITY_NORMALIZATION_PX = 1000.0  # 이 거리(픽셀) 이상이면 근접도 점수는 0에 수렴
_PROXIMITY_WEIGHT = 40.0
_CONFIDENCE_WEIGHT = 10.0

_TRIAGE_EVENTS = {WorkerEvent.PROLONGED_PRESENCE, WorkerEvent.TRACKING_LOST}


@dataclass
class PriorityBreakdown:
    track_id: str
    total_score: float
    duration_minutes: float | None
    duration_score: float
    distance_px: float | None
    proximity_score: float
    confidence_score: float


def _zone_centroid(zone_map: ZoneMapConfig, zone_id: str | None) -> tuple[float, float] | None:
    if zone_id is None:
        return None
    for zone in zone_map.zones:
        if zone.zone_id == zone_id and zone.polygon:
            xs = [p[0] for p in zone.polygon]
            ys = [p[1] for p in zone.polygon]
            return (sum(xs) / len(xs), sum(ys) / len(ys))
    return None


def _status_since(worker: WorkerStatus, log_entries: list[WorkerEventLogEntry]) -> str | None:
    """worker.event로 가장 최근에 바뀐 시각을 로그에서 찾는다(같은 event가 여러 번 등장할 수
    있으므로 track_id 로그 중 마지막으로 이 event가 된 지점을 찾는다)."""
    for entry in reversed(log_entries):
        if entry.event == worker.event:
            return entry.at
    return None


def compute_priority(
    worker: WorkerStatus,
    *,
    now: datetime,
    fire_zone_id: str | None,
    zone_map: ZoneMapConfig,
    log_entries: list[WorkerEventLogEntry],
) -> PriorityBreakdown | None:
    """PROLONGED_PRESENCE/TRACKING_LOST가 아니면(확인이 급하지 않으면) None을 반환한다."""
    if worker.event not in _TRIAGE_EVENTS:
        return None

    since_iso = _status_since(worker, log_entries)
    duration_minutes: float | None = None
    duration_score = 0.0
    if since_iso is not None:
        duration_minutes = max(0.0, (now - datetime.fromisoformat(since_iso)).total_seconds() / 60)
        duration_score = min(duration_minutes / _DURATION_CAP_MINUTES, 1.0) * _DURATION_WEIGHT

    worker_point = _zone_centroid(zone_map, worker.last_zone)
    fire_point = _zone_centroid(zone_map, fire_zone_id)
    distance_px: float | None = None
    proximity_score = _PROXIMITY_WEIGHT / 2  # 구역 좌표를 모르면(둘 중 하나라도 없으면) 중립값
    if worker_point is not None and fire_point is not None:
        distance_px = math.dist(worker_point, fire_point)
        proximity_score = max(0.0, 1.0 - min(distance_px / _PROXIMITY_NORMALIZATION_PX, 1.0)) * _PROXIMITY_WEIGHT

    confidence_score = (worker.confidence if worker.confidence is not None else 0.5) * _CONFIDENCE_WEIGHT

    total = duration_score + proximity_score + confidence_score
    return PriorityBreakdown(
        track_id=worker.track_id,
        total_score=round(total, 1),
        duration_minutes=round(duration_minutes, 1) if duration_minutes is not None else None,
        duration_score=round(duration_score, 1),
        distance_px=round(distance_px, 1) if distance_px is not None else None,
        proximity_score=round(proximity_score, 1),
        confidence_score=round(confidence_score, 1),
    )


def rank_workers(
    workers: list[WorkerStatus],
    *,
    now: datetime,
    fire_zone_id: str | None,
    zone_map: ZoneMapConfig,
    log_loader,
    camera_id: str,
) -> list[PriorityBreakdown]:
    """확인이 필요한(PROLONGED_PRESENCE/TRACKING_LOST) 작업자만 점수 내림차순으로 정렬해 반환.

    log_loader: (camera_id, track_id) -> list[WorkerEventLogEntry] 시그니처의 함수
    (app.rules.worker_log.load_worker_log를 그대로 넘겨 쓴다 — 테스트에서는 가짜로 교체 가능).
    """
    results = []
    for w in workers:
        entries = log_loader(camera_id, w.track_id)
        breakdown = compute_priority(w, now=now, fire_zone_id=fire_zone_id, zone_map=zone_map, log_entries=entries)
        if breakdown is not None:
            results.append(breakdown)
    return sorted(results, key=lambda b: b.total_score, reverse=True)
