from dataclasses import dataclass, field

import numpy as np

import app.inference.situation_probe as situation_probe_module
from app.inference.situation_probe import STAY_CATEGORY, probe_situation, probe_zone_situation


@dataclass
class _FakeGeometry:
    x: float
    y: float
    w: float
    h: float
    type: str = "bbox"


@dataclass
class _FakePrediction:
    class_name: str
    confidence: float = 0.5
    geometry: _FakeGeometry | None = None


@dataclass
class _FakePredictResult:
    predictions: list = field(default_factory=list)


class _FakeFoundation:
    def __init__(self, predictions):
        self._predictions = predictions
        self.last_call = None

    def predict(self, key, *, image, text_prompts, confidence):
        self.last_call = {"key": key, "text_prompts": text_prompts, "confidence": confidence}
        return _FakePredictResult(predictions=self._predictions)


class _FakeClient:
    def __init__(self, predictions):
        self.foundation = _FakeFoundation(predictions)


def _frame():
    return np.zeros((10, 10, 3), dtype=np.uint8)


def test_probe_returns_none_when_no_prompt_matches(monkeypatch):
    fake_client = _FakeClient(predictions=[])
    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: fake_client)

    result = probe_situation(_frame(), ["쓰러진 사람"])

    assert result is None
    assert fake_client.foundation.last_call["text_prompts"] == ["쓰러진 사람"]


def test_probe_composes_sentence_from_matched_prompts(monkeypatch):
    predictions = [_FakePrediction("쓰러진 사람", 0.6), _FakePrediction("연기에 둘러싸인 사람", 0.4)]
    fake_client = _FakeClient(predictions=predictions)
    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: fake_client)

    result = probe_situation(_frame(), ["쓰러진 사람", "연기에 둘러싸인 사람", "바닥에 누워있는 사람"])

    assert result is not None
    assert "쓰러진 사람" in result
    assert "연기에 둘러싸인 사람" in result


def test_probe_ignores_predictions_outside_prompt_list(monkeypatch):
    """ZERO가 우리가 안 물어본 클래스를 반환해도(다른 호출과 혼선 등) 무시해야 한다."""
    predictions = [_FakePrediction("person", 0.9)]
    fake_client = _FakeClient(predictions=predictions)
    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: fake_client)

    result = probe_situation(_frame(), ["쓰러진 사람"])

    assert result is None


def test_probe_returns_none_on_call_failure(monkeypatch):
    class _RaisingClient:
        @property
        def foundation(self):
            raise RuntimeError("network error")

    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: _RaisingClient())

    result = probe_situation(_frame(), ["쓰러진 사람"])

    assert result is None


def test_probe_zone_situation_matches_nearest_worker(monkeypatch):
    # W1은 (0,0,10,10)(중심 5,5) 근처, W2는 (500,500,510,510)(중심 505,505) — 서로 아주 멀다.
    # ZERO가 찾은 "쓰러진 사람" 박스가 W1 중심 바로 옆이므로 W1에만 매칭돼야 한다.
    predictions = [_FakePrediction("쓰러진 사람", 0.6, _FakeGeometry(x=2, y=2, w=6, h=6))]
    fake_client = _FakeClient(predictions=predictions)
    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: fake_client)

    workers_by_zone = {"A구역": [("W1", (0.0, 0.0, 10.0, 10.0)), ("W2", (500.0, 500.0, 510.0, 510.0))]}
    breakdown, matched = probe_zone_situation(_frame(), workers_by_zone)

    assert breakdown["A구역"] == {STAY_CATEGORY: 1, "쓰러진 사람": 1}
    assert matched == {"W1": "쓰러진 사람"}


def test_probe_zone_situation_no_match_beyond_distance_falls_back_to_stay(monkeypatch):
    predictions = [_FakePrediction("쓰러진 사람", 0.6, _FakeGeometry(x=1000, y=1000, w=10, h=10))]
    fake_client = _FakeClient(predictions=predictions)
    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: fake_client)

    workers_by_zone = {"A구역": [("W1", (0.0, 0.0, 10.0, 10.0))]}
    breakdown, matched = probe_zone_situation(_frame(), workers_by_zone, match_distance_px=50.0)

    assert breakdown["A구역"] == {STAY_CATEGORY: 1}
    assert matched == {}


def test_probe_zone_situation_call_failure_falls_back_to_stay_only(monkeypatch):
    class _RaisingClient:
        @property
        def foundation(self):
            raise RuntimeError("network error")

    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: _RaisingClient())

    workers_by_zone = {"A구역": [("W1", (0.0, 0.0, 10.0, 10.0))], "B구역": [("W2", (0.0, 0.0, 10.0, 10.0))]}
    breakdown, matched = probe_zone_situation(_frame(), workers_by_zone)

    assert breakdown == {"A구역": {STAY_CATEGORY: 1}, "B구역": {STAY_CATEGORY: 1}}
    assert matched == {}


def test_probe_zone_situation_empty_workers_returns_empty(monkeypatch):
    fake_client = _FakeClient(predictions=[])
    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: fake_client)

    breakdown, matched = probe_zone_situation(_frame(), {})

    assert breakdown == {}
    assert matched == {}


def test_probe_zone_situation_totals_always_equal_zone_member_count(monkeypatch):
    """카테고리 합계는 항상 그 구역의 사람 수와 같아야 한다(체류중으로라도 전부 분류되므로)."""
    predictions = [
        _FakePrediction("쓰러진 사람", 0.6, _FakeGeometry(x=2, y=2, w=6, h=6)),
        _FakePrediction("연기에 둘러싸인 사람", 0.5, _FakeGeometry(x=52, y=2, w=6, h=6)),
    ]
    fake_client = _FakeClient(predictions=predictions)
    monkeypatch.setattr(situation_probe_module, "get_bdai_client", lambda: fake_client)

    workers_by_zone = {
        "A구역": [
            ("W1", (0.0, 0.0, 10.0, 10.0)),
            ("W2", (50.0, 0.0, 60.0, 10.0)),
            ("W3", (200.0, 200.0, 210.0, 210.0)),
        ]
    }
    breakdown, matched = probe_zone_situation(_frame(), workers_by_zone)

    assert sum(breakdown["A구역"].values()) == 3
    assert matched["W1"] == "쓰러진 사람"
    assert matched["W2"] == "연기에 둘러싸인 사람"
    assert "W3" not in matched
