import pytest

from app.rules.ppe_violation_log import format_violation_text, load_ppe_violation_log, record_if_new_violation, reset_streams


@pytest.fixture(autouse=True)
def _reset_open_streams():
    """`_open_streams`는 모듈 전역이라 테스트 간에 그대로 남는다 — 앞선 테스트가 만든
    스트림이 뒤 테스트의 "같은 위치인지" 판단에 섞여 들어가는 걸 막는다(실측: 파일 단위로
    실행하면 실패하는데 단일 테스트로 실행하면 통과하는 순서 의존성이 있었다)."""
    reset_streams()
    yield


def _record(*, camera_id="cam-1", zone="A구역", violations, at, bbox=(10.0, 20.0, 30.0, 40.0), **kwargs):
    record_if_new_violation(
        camera_id,
        zone=zone,
        violations=violations,
        now_iso=at,
        frame_path=f"/demo-frames/frames/{at}.jpg",
        bbox_xyxy=bbox,
        confidence=0.9,
        **kwargs,
    )


def test_first_violation_is_logged(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record(violations=["helmet"], at="2026-01-01T12:00:00")

    log = load_ppe_violation_log("cam-1")
    assert len(log) == 1
    assert log[0].violations == ["helmet"]
    assert log[0].bbox_xyxy == (10.0, 20.0, 30.0, 40.0)


def test_continuing_violation_at_same_spot_is_not_logged_again(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record(violations=["helmet"], at="2026-01-01T12:00:00", bbox=(10.0, 20.0, 30.0, 40.0))
    _record(violations=["helmet"], at="2026-01-01T12:00:05", bbox=(11.0, 21.0, 31.0, 41.0))  # 거의 같은 위치

    assert len(load_ppe_violation_log("cam-1")) == 1


def test_different_position_logs_separately_even_within_cooldown(tmp_path, monkeypatch):
    """같은 구역·같은 시간대라도 위치가 멀면(다른 사람일 가능성) 별도로 기록된다 —
    추적 ID 없이 위치만으로 구분한다는 설계."""
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record(violations=["helmet"], at="2026-01-01T12:00:00", bbox=(10.0, 20.0, 30.0, 40.0))
    _record(violations=["helmet"], at="2026-01-01T12:00:05", bbox=(500.0, 500.0, 530.0, 540.0))

    assert len(load_ppe_violation_log("cam-1")) == 2


def test_violation_combination_change_logs_new_entry(tmp_path, monkeypatch):
    """같은 위치라도 위반 조합이 바뀌면(헬멧만 → 헬멧+조끼) 새로 기록해야 한다."""
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record(violations=["helmet"], at="2026-01-01T12:00:00")
    _record(violations=["helmet", "vest"], at="2026-01-01T12:00:05")

    log = load_ppe_violation_log("cam-1")
    assert len(log) == 2
    assert log[1].violations == ["helmet", "vest"]


def test_same_spot_after_cooldown_expires_logs_again(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record(violations=["vest"], at="2026-01-01T12:00:00", bbox=(10.0, 20.0, 30.0, 40.0), cooldown_seconds=10.0)
    _record(violations=["vest"], at="2026-01-01T12:00:20", bbox=(10.0, 20.0, 30.0, 40.0), cooldown_seconds=10.0)  # 20초 후, 쿨다운(10초) 지남

    assert len(load_ppe_violation_log("cam-1")) == 2


def test_empty_violations_records_nothing(tmp_path, monkeypatch):
    import app.rules.ppe_violation_log as log_module

    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path)

    _record(violations=[], at="2026-01-01T12:00:00")

    assert load_ppe_violation_log("cam-1") == []


def test_format_violation_text():
    assert format_violation_text(["helmet"]) == "헬멧 미착용"
    assert format_violation_text(["vest"]) == "조끼 미착용"
    assert format_violation_text(["helmet", "vest"]) == "헬멧, 조끼 미착용"
