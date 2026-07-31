from dataclasses import dataclass, field

import numpy as np

import app.inference.situation_probe as situation_probe_module
from app.inference.situation_probe import probe_situation


@dataclass
class _FakePrediction:
    class_name: str
    confidence: float = 0.5


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
