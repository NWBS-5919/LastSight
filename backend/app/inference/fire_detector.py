"""화재/연기 탐지.

2026-07-31: fire-smoke-v4-detection(rf-detr-nano, 박스 탐지 태스크)을 학습해 BDAI에
배포까지 했다(검증 지표: 전체 F1 0.897, mAP50 0.891). `FIRE_SMOKE_DEPLOYMENT_ID`가
설정돼 있으면 이 커스텀 모델을 쓰고, 없으면 ZERO(제로샷 파운데이션 모델)에
"fire"/"smoke" 텍스트 프롬프트로 묻는 방식으로 폴백한다. v1(세그멘테이션, F1 0.15)·
v3(세그멘테이션, F1 0.005)는 태스크를 세그멘테이션으로 잡은 게 원인으로 보이는
실패였고, v4에서 박스 탐지로 바꾸며 검증 지표상으로는 해결됐다.

다만 학습 데이터가 영상 8개 클립에서만 나와 장면 다양성이 부족했던 탓에, 검증 지표는
좋아도 실제로는 ZERO보다 일반화가 떨어지는 것으로 확인돼 `.env`에서
`FIRE_SMOKE_DEPLOYMENT_ID`를 비워 기본은 ZERO를 쓰도록 되돌렸다(development_log.md
32번 참고). 배포 자체는 BDAI에 남아있어 값만 다시 채우면 즉시 재활성화된다.

주의(SDK 소스 docstring): ZERO는 플랫폼이 스케줄에 따라 켜고 끄는 공유 엔드포인트라
워밍업 중이거나 오프아워면 UnavailableError(503)가 날 수 있다. 실시간 파이프라인에서는
호출 실패를 알람 미발생으로 조용히 삼키지 말고 상위에서 재시도/로그 처리할 것.
"""

import base64
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.bdai_client import get_bdai_client
from app.core.config import get_settings
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


def _parse_detections(predictions) -> list[FireDetection]:
    detections: list[FireDetection] = []
    for p in predictions:
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


def detect(frame: np.ndarray, confidence_threshold: float | None = None) -> list[FireDetection]:
    """단일 프레임(BGR numpy array, cv2로 읽은 형태)에서 fire/smoke를 탐지.

    confidence_threshold를 안 주면: 커스텀 모델은 학습 결과가 보고한
    optimal_confidence(0.4419)를, ZERO 폴백은 0.3을 기본값으로 쓴다.
    """
    settings = get_settings()
    client = get_bdai_client()
    image_b64 = _encode_frame(frame)

    if settings.fire_smoke_deployment_id:
        result = client.deployments.predict(
            settings.fire_smoke_deployment_id,
            image_b64=image_b64,
            confidence=confidence_threshold if confidence_threshold is not None else 0.4419,
        )
        return _parse_detections(result.predictions)

    result = client.foundation.predict(
        "zero",
        image={"image_b64": image_b64},
        text_prompts=list(_PROMPT_TO_CLASS.keys()),
        confidence=confidence_threshold if confidence_threshold is not None else 0.3,
    )
    return _parse_detections(result.predictions)
