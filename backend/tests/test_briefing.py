from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.inference.briefing import (
    TimeHint,
    _build_context_text,
    _kst_str,
    _strip_markdown,
    find_frame_near,
    parse_time_hint,
    resolve_time_hint,
)
from app.models.schemas import PpeViolationLogEntry, ZoneSituationEntry, ZoneSituationLogEntry

KST = ZoneInfo("Asia/Seoul")


def _now_kst_evening() -> datetime:
    """KST 오후 9시대인 UTC 시각 — 오전/오후 생략 표현 테스트에 쓴다."""
    return datetime(2026, 8, 5, 12, 55, 24, tzinfo=UTC)  # KST 21:55:24


def test_parse_time_hint_scenario_relative_seconds():
    hint = parse_time_hint("74초쯤에 무슨 일이 있었어?", _now_kst_evening())
    assert hint == TimeHint(kind="scenario", value=74.0)


def test_parse_time_hint_minutes_and_seconds():
    hint = parse_time_hint("1분 20초쯤 어땠어", _now_kst_evening())
    assert hint == TimeHint(kind="scenario", value=80.0)


def test_parse_time_hint_fire_relative():
    hint = parse_time_hint("화재 나고 12초 후에는?", _now_kst_evening())
    assert hint == TimeHint(kind="fire", value=12.0)


def test_parse_time_hint_absolute_with_ampm():
    hint = parse_time_hint("오후 9시 55분쯤 사람들 뭐하고 있었어?", _now_kst_evening())
    assert hint == TimeHint(kind="absolute", value=(21, 55))


def test_parse_time_hint_absolute_am_explicit():
    hint = parse_time_hint("오전 9시 5분에는 어땠어", _now_kst_evening())
    assert hint == TimeHint(kind="absolute", value=(9, 5))


def test_parse_time_hint_absolute_infers_ampm_from_now():
    # 오전/오후를 안 밝혀도, 지금이 저녁(오후 9시대)이면 "9시"를 오후로 추정해야 한다.
    hint = parse_time_hint("9시 55분에 뭐였어", _now_kst_evening())
    assert hint == TimeHint(kind="absolute", value=(21, 55))


def test_parse_time_hint_returns_none_without_time_reference():
    assert parse_time_hint("지금 상황 어때?", _now_kst_evening()) is None
    assert parse_time_hint("오늘 미착용한 인원 몇 명이야?", _now_kst_evening()) is None


def test_resolve_time_hint_scenario_adds_offset_to_scenario_start():
    scenario_started_at = datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC)
    resolved = resolve_time_hint(
        TimeHint(kind="scenario", value=74.0),
        now=_now_kst_evening(),
        scenario_started_at=scenario_started_at,
        fire_triggered_at=None,
    )
    assert resolved == scenario_started_at + timedelta(seconds=74)


def test_resolve_time_hint_fire_adds_offset_to_fire_time():
    fire_triggered_at = datetime(2026, 8, 5, 12, 0, 8, tzinfo=UTC)
    resolved = resolve_time_hint(
        TimeHint(kind="fire", value=12.0),
        now=_now_kst_evening(),
        scenario_started_at=datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC),
        fire_triggered_at=fire_triggered_at,
    )
    assert resolved == fire_triggered_at + timedelta(seconds=12)


def test_resolve_time_hint_fire_returns_none_if_fire_not_triggered_yet():
    resolved = resolve_time_hint(
        TimeHint(kind="fire", value=12.0),
        now=_now_kst_evening(),
        scenario_started_at=datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC),
        fire_triggered_at=None,
    )
    assert resolved is None


def test_resolve_time_hint_absolute_converts_kst_to_utc():
    resolved = resolve_time_hint(
        TimeHint(kind="absolute", value=(21, 55)),
        now=_now_kst_evening(),
        scenario_started_at=datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC),
        fire_triggered_at=None,
    )
    assert resolved is not None
    assert resolved.astimezone(KST).hour == 21
    assert resolved.astimezone(KST).minute == 55


def _situation_entry(at: str, frame_path: str = "/demo-frames/frames/0074.jpg") -> ZoneSituationLogEntry:
    return ZoneSituationLogEntry(
        camera_id="demo-camera",
        at=at,
        zones=[ZoneSituationEntry(zone_id="B구역", total=2, breakdown={"체류중": 1, "쓰러진 사람": 1})],
        frame_path=frame_path,
    )


def _ppe_entry(at: str, frame_path: str = "/demo-frames/frames/0015.jpg") -> PpeViolationLogEntry:
    return PpeViolationLogEntry(
        id="ppe-1", violations=["helmet"], zone="A구역", at=at, frame_path=frame_path,
        bbox_xyxy=None, confidence=0.8, helmet_state="not_worn", vest_state="worn",
    )


def test_find_frame_near_prefers_nearby_situation_check():
    target = datetime(2026, 8, 5, 12, 1, 15, tzinfo=UTC)
    situation_checks = [_situation_entry(at="2026-08-05T12:01:14+00:00")]
    path, note = find_frame_near(
        target, scenario_started_at=datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC),
        situation_checks=situation_checks, ppe_events=[],
    )
    assert path == "/demo-frames/frames/0074.jpg"
    assert note is not None and "쓰러진 사람" in note


def test_find_frame_near_falls_back_to_ppe_event_when_no_close_situation_check():
    target = datetime(2026, 8, 5, 12, 0, 15, tzinfo=UTC)
    situation_checks = [_situation_entry(at="2026-08-05T12:05:00+00:00")]  # 너무 멀어서 채택 안 됨
    ppe_events = [_ppe_entry(at="2026-08-05T12:00:14+00:00")]
    path, note = find_frame_near(
        target, scenario_started_at=datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC),
        situation_checks=situation_checks, ppe_events=ppe_events,
    )
    assert path == "/demo-frames/frames/0015.jpg"
    assert note is not None and "헬멧" in note


def test_find_frame_near_falls_back_to_scenario_frames_when_nothing_logged_nearby():
    target = datetime(2026, 8, 5, 12, 0, 45, tzinfo=UTC)
    path, note = find_frame_near(
        target, scenario_started_at=datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC),
        situation_checks=[], ppe_events=[],
    )
    assert path is not None and path.startswith("/demo-frames/frames/")
    assert note is None  # scenario.json 프레임엔 사건 정보가 없다


def test_build_context_text_includes_all_ppe_events_not_just_last_three():
    events = [_ppe_entry(at=f"2026-08-05T12:00:{i:02d}+00:00") for i in range(5)]
    text = _build_context_text(
        now=datetime(2026, 8, 5, 12, 5, 0, tzinfo=UTC),
        fire_alert=None,
        zone_person_counts={},
        situation_checks=[],
        ppe_events=events,
    )
    assert text.count("헬멧=not_worn") == 5


def test_build_context_text_shows_kst_not_utc():
    # UTC 12:00 = KST 21:00 — 화면에 표시되는 시각(KST)과 챗봇이 말하는 시각이 어긋나면 안 된다.
    text = _build_context_text(
        now=datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC),
        fire_alert=None,
        zone_person_counts={},
        situation_checks=[],
        ppe_events=[],
    )
    assert "21:00:00" in text
    assert "12:00:00" not in text


def test_kst_str_converts_utc_to_kst():
    assert _kst_str(datetime(2026, 8, 5, 12, 55, 24, tzinfo=UTC)) == "2026-08-05 21:55:24"


def test_strip_markdown_removes_bold_headers_bullets_and_hr():
    raw = "### 상황 요약\n* **화재 발생**: B구역\n---\n1. 첫 번째 항목\n2. 두 번째 항목"
    cleaned = _strip_markdown(raw)
    assert "#" not in cleaned
    assert "*" not in cleaned
    assert "---" not in cleaned
    assert "화재 발생: B구역" in cleaned
    assert "1." not in cleaned and "2." not in cleaned


def test_strip_markdown_leaves_plain_sentences_untouched():
    raw = "B구역에서 화재가 발생했습니다. 현재 2명이 관측되고 있습니다."
    assert _strip_markdown(raw) == raw


def test_strip_markdown_removes_single_asterisk_emphasis():
    raw = "*모든 작업자가 안전모를 착용하고 있습니다.*"
    cleaned = _strip_markdown(raw)
    assert "*" not in cleaned
    assert cleaned == "모든 작업자가 안전모를 착용하고 있습니다."


def test_strip_markdown_removes_emoji():
    raw = "🚨 안전 및 화재 상황\n👥 인원 관측 현황: 2명"
    cleaned = _strip_markdown(raw)
    assert "🚨" not in cleaned
    assert "👥" not in cleaned
    assert "인원 관측 현황: 2명" in cleaned
