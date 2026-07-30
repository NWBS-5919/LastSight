from datetime import datetime, timedelta

from app.models.schemas import WorkerEvent
from app.rules.state_engine import PROLONGED_PRESENCE_MINUTES, resolve_status

NOW = datetime(2026, 1, 1, 12, 0, 0)


def test_no_fire_and_observed_is_inside_observed():
    status = resolve_status("P01", is_currently_observed=True, now=NOW, fire_triggered_at=None)
    assert status.event == WorkerEvent.INSIDE_OBSERVED


def test_observed_soon_after_fire_is_inside_observed():
    fire_at = NOW - timedelta(minutes=1)
    status = resolve_status("P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at)
    assert status.event == WorkerEvent.INSIDE_OBSERVED


def test_observed_past_threshold_after_fire_is_prolonged_presence():
    fire_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES + 1)
    status = resolve_status("P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at)
    assert status.event == WorkerEvent.PROLONGED_PRESENCE


def test_exactly_at_threshold_is_prolonged_presence():
    fire_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES)
    status = resolve_status("P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at)
    assert status.event == WorkerEvent.PROLONGED_PRESENCE


def test_not_observed_is_tracking_lost_regardless_of_fire():
    status = resolve_status("P01", is_currently_observed=False, now=NOW, fire_triggered_at=None)
    assert status.event == WorkerEvent.TRACKING_LOST

    fire_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES + 10)
    status2 = resolve_status("P01", is_currently_observed=False, now=NOW, fire_triggered_at=fire_at)
    assert status2.event == WorkerEvent.TRACKING_LOST


def test_not_observed_never_implies_safety():
    # CLAUDE.md 절대 원칙: TRACKING_LOST는 안전 여부를 확정하지 않는다 — 그냥 "안 보임"일 뿐.
    status = resolve_status("P01", is_currently_observed=False, now=NOW)
    assert status.event == WorkerEvent.TRACKING_LOST
    assert status.event != WorkerEvent.INSIDE_OBSERVED


def test_camera_failure_overrides_everything():
    fire_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES + 10)
    status = resolve_status("P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at, camera_ok=False)
    assert status.event == WorkerEvent.CAMERA_FAILURE

    status2 = resolve_status("P01", is_currently_observed=False, now=NOW, camera_ok=False)
    assert status2.event == WorkerEvent.CAMERA_FAILURE


def test_status_carries_last_known_fields():
    status = resolve_status(
        "P01",
        is_currently_observed=False,
        now=NOW,
        last_zone="B구역",
        last_seen_at="2026-01-01T11:55:00",
        last_frame_path="/frames/p01.jpg",
    )
    assert status.last_zone == "B구역"
    assert status.last_seen_at == "2026-01-01T11:55:00"
    assert status.last_frame_path == "/frames/p01.jpg"
