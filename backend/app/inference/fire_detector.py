"""화재/연기 탐지 — BDAI의 ZERO(제로샷 파운데이션 모델)를 프롬프트로 사용.

전용 fire/smoke 데이터셋을 따로 학습하지 않고, ZERO에 "fire"/"smoke" 텍스트 프롬프트로
바로 물어보는 방식(MVP 1차 접근). 정확도가 부족하면 그때 Fire and Smoke Segmentation
데이터셋(docs 조사 결과) 등으로 커스텀 모델을 학습해 이 함수만 교체하면 된다 —
바깥(app.rules.alarm_trigger)에서는 detect()의 반환 타입만 알면 되므로 교체 비용이 낮음.

주의(SDK 소스 docstring): ZERO는 플랫폼이 스케줄에 따라 켜고 끄는 공유 엔드포인트라
워밍업 중이거나 오프아워면 UnavailableError(503)가 날 수 있다. 실시간 파이프라인에서는
호출 실패를 알람 미발생으로 조용히 삼키지 말고 상위에서 재시도/로그 처리할 것.
"""

import base64
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.bdai_client import get_bdai_client
from app.models.schemas import ObjectClass

_PROMPT_TO_CLASS = {
    "fire": ObjectClass.FIRE,
    "smoke": ObjectClass.SMOKE,
}


@dataclass
class FireDetection:
    object_class: ObjectClass  # FIRE 또는 SMOKE
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]


def _encode_frame(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("프레임을 JPEG로 인코딩하지 못했습니다.")
    return base64.b64encode(buf).decode("ascii")


def detect(frame: np.ndarray, confidence_threshold: float = 0.3) -> list[FireDetection]:
    """단일 프레임(BGR numpy array, cv2로 읽은 형태)에서 fire/smoke를 탐지."""
    client = get_bdai_client()
    image_b64 = _encode_frame(frame)

    result = client.foundation.predict(
        "zero",
        image={"image_b64": image_b64},
        text_prompts=list(_PROMPT_TO_CLASS.keys()),
        confidence=confidence_threshold,
    )

    detections: list[FireDetection] = []
    for p in result.predictions:
        object_class = _PROMPT_TO_CLASS.get(p.class_name.lower())
        if object_class is None or p.geometry.type != "bbox":
            continue
        x, y, w, h = p.geometry.x, p.geometry.y, p.geometry.w, p.geometry.h
        detections.append(
            FireDetection(
                object_class=object_class,
                confidence=p.confidence,
                bbox_xyxy=(x, y, x + w, y + h),
            )
        )
    return detections
