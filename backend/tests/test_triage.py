from datetime import datetime

from app.models.schemas import WorkerEvent, WorkerEventLogEntry, WorkerStatus, ZoneDef, ZoneMapConfig
from app.rules.triage import compute_priority, rank_workers

NOW = datetime.fromisoformat("2026-01-01T12:30:00")

ZONE_MAP = ZoneMapConfig(
    camera_id="cam-1",
    zones=[
        ZoneDef(zone_id="fire-zone", polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),  # centroid (50, 50)
        ZoneDef(zone_id="near-zone", polygon=[(100, 0), (200, 0), (200, 100), (100, 100)]),  # centroid (150, 50)
        ZoneDef(zone_id="far-zone", polygon=[(900, 900), (1000, 900), (1000, 1000), (900, 1000)]),  # centroid (950, 950)
    ],
)


def test_inside_observed_is_not_triaged():
    worker = WorkerStatus(track_id="P01", event=WorkerEvent.INSIDE_OBSERVED, last_zone="fire-zone")
    result = compute_priority(worker, now=NOW, fire_zone_id="fire-zone", zone_map=ZONE_MAP, log_entries=[])
    assert result is None


def test_closer_zone_scores_higher_than_farther_zone_for_same_duration():
    log = [WorkerEventLogEntry(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, at="2026-01-01T12:20:00")]

    near = WorkerStatus(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="near-zone", confidence=0.8)
    far = WorkerStatus(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="far-zone", confidence=0.8)

    near_score = compute_priority(near, now=NOW, fire_zone_id="fire-zone", zone_map=ZONE_MAP, log_entries=log)
    far_score = compute_priority(far, now=NOW, fire_zone_id="fire-zone", zone_map=ZONE_MAP, log_entries=log)

    assert near_score.total_score > far_score.total_score
    assert near_score.distance_px < far_score.distance_px


def test_longer_duration_scores_higher_than_shorter_for_same_zone():
    short_log = [WorkerEventLogEntry(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, at="2026-01-01T12:29:00")]
    long_log = [WorkerEventLogEntry(track_id="P02", event=WorkerEvent.PROLONGED_PRESENCE, at="2026-01-01T12:00:00")]

    short = WorkerStatus(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="fire-zone", confidence=0.8)
    long_ = WorkerStatus(track_id="P02", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="fire-zone", confidence=0.8)

    short_score = compute_priority(short, now=NOW, fire_zone_id="fire-zone", zone_map=ZONE_MAP, log_entries=short_log)
    long_score = compute_priority(long_, now=NOW, fire_zone_id="fire-zone", zone_map=ZONE_MAP, log_entries=long_log)

    assert long_score.total_score > short_score.total_score
    assert long_score.duration_minutes == 30.0  # 30분 상한(cap)에서 포화


def test_rank_workers_sorts_descending_and_excludes_inside_observed():
    log_store = {
        "P01": [WorkerEventLogEntry(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, at="2026-01-01T12:00:00")],
        "P02": [WorkerEventLogEntry(track_id="P02", event=WorkerEvent.PROLONGED_PRESENCE, at="2026-01-01T12:25:00")],
        "P03": [WorkerEventLogEntry(track_id="P03", event=WorkerEvent.INSIDE_OBSERVED, at="2026-01-01T12:00:00")],
    }
    workers = [
        WorkerStatus(track_id="P01", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="fire-zone", confidence=0.9),
        WorkerStatus(track_id="P02", event=WorkerEvent.PROLONGED_PRESENCE, last_zone="far-zone", confidence=0.9),
        WorkerStatus(track_id="P03", event=WorkerEvent.INSIDE_OBSERVED, last_zone="fire-zone", confidence=0.9),
    ]

    ranked = rank_workers(
        workers,
        now=NOW,
        fire_zone_id="fire-zone",
        zone_map=ZONE_MAP,
        log_loader=lambda camera_id, track_id: log_store[track_id],
        camera_id="cam-1",
    )

    assert [r.track_id for r in ranked] == ["P01", "P02"]  # P03(inside_observed) 제외, 점수 내림차순
    assert ranked[0].total_score >= ranked[1].total_score
