from dataclasses import dataclass, field

import numpy as np
import pytest

import app.inference.detector as detector_module
from app.models.schemas import ObjectClass


@dataclass
class _FakeGeometry:
    type: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class _FakePrediction:
    class_name: str
    confidence: float
    geometry: _FakeGeometry


@dataclass
class _FakePredictResponse:
    predictions: list = field(default_factory=list)


class _FakeDeployments:
    def __init__(self, predictions):
        self._predictions = predictions
        self.last_call = None

    def predict(self, deployment_id, *, image_b64, confidence):
        self.last_call = {"deployment_id": deployment_id, "confidence": confidence}
        return _FakePredictResponse(predictions=self._predictions)


class _FakeClient:
    def __init__(self, predictions):
        self.deployments = _FakeDeployments(predictions)


class _FakeSettings:
    def __init__(self, ppe_deployment_id):
        self.ppe_deployment_id = ppe_deployment_id


def _frame():
    return np.zeros((10, 10, 3), dtype=np.uint8)


def test_detect_maps_predictions_and_filters_unmapped_classes(monkeypatch):
    predictions = [
        _FakePrediction("person", 0.95, _FakeGeometry("bbox", 10, 20, 30, 40)),
        _FakePrediction("helmet", 0.9, _FakeGeometry("bbox", 1, 2, 3, 4)),
        # 학습 스키마엔 등록됐지만 실제 학습 데이터가 없던(support=0) 속성 클래스 — 매핑에 없으니 무시돼야 함
        _FakePrediction("상의 색상", 0.5, _FakeGeometry("bbox", 0, 0, 1, 1)),
    ]
    fake_client = _FakeClient(predictions)
    monkeypatch.setattr(detector_module, "get_bdai_client", lambda: fake_client)
    monkeypatch.setattr(detector_module, "get_settings", lambda: _FakeSettings("dep-123"))

    results = detector_module.detect(_frame())

    assert len(results) == 2
    assert results[0].object_class == ObjectClass.PERSON
    assert results[0].confidence == 0.95
    assert results[0].bbox_xyxy == (10, 20, 40, 60)
    assert results[1].object_class == ObjectClass.HELMET
    assert fake_client.deployments.last_call["deployment_id"] == "dep-123"


def test_detect_raises_without_deployment_id(monkeypatch):
    monkeypatch.setattr(detector_module, "get_settings", lambda: _FakeSettings(""))

    with pytest.raises(RuntimeError):
        detector_module.detect(_frame())
