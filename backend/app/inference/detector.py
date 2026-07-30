"""탐지 모델 추론 래퍼 — BDAI에 배포된 PPE(person/helmet/vest) 모델을 호출한다.

fire_detector.py가 ZERO 제로샷 모델을 프롬프트로 호출하는 것과 달리, 이 모델은
`ppe-v2-smoke-augmented`로 직접 학습시킨 모델이라 먼저 BDAI에 배포(deployment)해둬야
한다 — 배포 ID는 `.env`의 `PPE_DEPLOYMENT_ID`로 주입한다(app.core.config.Settings).

CLAUDE.md 4-1 클래스 정의(person/helmet/vest)를 그대로 따를 것. 학습 시 라벨 스키마에
같이 등록됐던 속성 라벨(상의 색상/가시성/안전모 색상/안전조끼 색상)은 실제 학습 데이터가
없어(support=0) 예측에 나오지 않지만, 혹시 나오더라도 매핑 테이블에 없으면 무시한다.
"""

import base64
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.bdai_client import get_bdai_client
from app.core.config import get_settings
from app.models.schemas import ObjectClass

_CLASS_NAME_TO_OBJECT_CLASS = {
    "person": ObjectClass.PERSON,
    "helmet": ObjectClass.HELMET,
    "vest": ObjectClass.VEST,
}


@dataclass
class Detection:
    object_class: ObjectClass
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]


def _encode_frame(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("프레임을 JPEG로 인코딩하지 못했습니다.")
    return base64.b64encode(buf).decode("ascii")


def detect(frame: np.ndarray, confidence_threshold: float = 0.5) -> list[Detection]:
    """단일 프레임(BGR numpy array, cv2로 읽은 형태)에서 person/helmet/vest를 탐지.

    confidence_threshold 기본값 0.5는 학습 결과가 보고한 optimal_confidence(0.5065)에 맞춘 값.
    """
    settings = get_settings()
    if not settings.ppe_deployment_id:
        raise RuntimeError(
            "PPE_DEPLOYMENT_ID가 설정되지 않았습니다. BDAI에서 ppe-v2-smoke-augmented 모델을 "
            "배포한 뒤 .env에 배포 ID를 채워주세요."
        )

    client = get_bdai_client()
    image_b64 = _encode_frame(frame)

    result = client.deployments.predict(
        settings.ppe_deployment_id,
        image_b64=image_b64,
        confidence=confidence_threshold,
    )

    detections: list[Detection] = []
    for p in result.predictions:
        object_class = _CLASS_NAME_TO_OBJECT_CLASS.get(p.class_name)
        if object_class is None or p.geometry.type != "bbox":
            continue
        x, y, w, h = p.geometry.x, p.geometry.y, p.geometry.w, p.geometry.h
        detections.append(
            Detection(
                object_class=object_class,
                confidence=p.confidence,
                bbox_xyxy=(x, y, x + w, y + h),
            )
        )
    return detections
