from datetime import datetime, timedelta

from app.models.schemas import WorkerEvent
from app.rules.state_engine import PROLONGED_PRESENCE_MINUTES, resolve_status

NOW = datetime(2026, 1, 1, 12, 0, 0)


def test_no_fire_and_observed_is_inside_observed():
    status = resolve_status("P01", is_currently_observed=True, now=NOW, fire_triggered_at=None)
    assert status.event == WorkerEvent.INSIDE_OBSERVED


def test_observed_soon_after_fire_is_inside_observed():
    fire_at = NOW - timedelta(minutes=1)
    status = resolve_status(
        "P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at, first_seen_at=fire_at.isoformat()
    )
    assert status.event == WorkerEvent.INSIDE_OBSERVED


def test_observed_past_threshold_after_fire_is_prolonged_presence():
    # 2026-08-03: PROLONGED_PRESENCE는 이제 화재 시각이 아니라 "이 작업자가 처음 감지된
    # 시각"(first_seen_at) 기준으로 판정한다 — 방금 나타난 사람이 화재가 오래전이라는
    # 이유만으로 즉시 장기체류경고가 되는 걸 막기 위함(state_engine.py 주석 참고).
    fire_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES + 10)
    first_seen_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES + 1)
    status = resolve_status(
        "P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at, first_seen_at=first_seen_at.isoformat()
    )
    assert status.event == WorkerEvent.PROLONGED_PRESENCE


def test_exactly_at_threshold_is_prolonged_presence():
    fire_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES + 10)
    first_seen_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES)
    status = resolve_status(
        "P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at, first_seen_at=first_seen_at.isoformat()
    )
    assert status.event == WorkerEvent.PROLONGED_PRESENCE


def test_freshly_seen_worker_stays_inside_observed_even_long_after_fire():
    # 실측으로 확인한 회귀 케이스: 화재가 오래전에 터졌어도, 방금 처음 나타난 사람은
    # 자기 기준 관측 지속시간이 짧으므로 곧바로 PROLONGED_PRESENCE가 되면 안 된다.
    fire_at = NOW - timedelta(minutes=PROLONGED_PRESENCE_MINUTES + 10)
    status = resolve_status(
        "P01", is_currently_observed=True, now=NOW, fire_triggered_at=fire_at, first_seen_at=NOW.isoformat()
    )
    assert status.event == WorkerEvent.INSIDE_OBSERVED


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
