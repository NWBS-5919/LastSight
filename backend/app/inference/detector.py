"""탐지 모델 추론 래퍼 — BDAI에 배포된 PPE(person/helmet/vest) 모델을 호출한다.

fire_detector.py와 동일한 폴백 패턴: `PPE_DEPLOYMENT_ID`가 설정돼 있으면 그 커스텀
모델(v6-29k-capped, rf-detr-large)을 쓰고, 없으면 ZERO(제로샷 파운데이션 모델)에
"person"/"safety helmet"/"vest" 텍스트 프롬프트로 묻는 방식으로 폴백한다.

2026-08-02: v6-29k-capped 학습·배포 완료(mAP50 0.84, precision 0.89, recall 0.83,
55 epoch). `.env`의 `PPE_DEPLOYMENT_ID`를 채우면 이 커스텀 모델로 전환된다.

CLAUDE.md 4-1 클래스 정의(person/helmet/vest)를 그대로 따를 것. 학습 시 라벨 스키마에
같이 등록됐던 속성 라벨(상의 색상/가시성/안전모 색상/안전조끼 색상)은 실제 학습 데이터가
없어(support=0) 예측에 나오지 않지만, 혹시 나오더라도 매핑 테이블에 없으면 무시한다.
head/no_vest 클래스도 학습 스냅샷엔 있었지만(각각 2,325·2,155 인스턴스), 실측해보니
confidence=0.01(사실상 무필터)로 낮춰도 단 한 건도 예측에 안 나온다 — 다른 클래스 대비
훨씬 적은 데이터로 학습돼 이 모델에서는 사실상 못 쓴다(head+helmet 기하학적 판정은
`app.rules.ppe_compliance`가 ZERO 폴백에서만 쓰고, 커스텀 모델 배포 시엔
`detect_head_upper_body()`가 호출 자체를 건너뛰므로 이 한계가 실제 판정에 영향은 없다 —
다만 head 신호가 없다는 뜻이라 커스텀 모델에서도 helmet 미착용 확정은 아직 안 된다).
"""

import base64
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.bdai_client import get_bdai_client
from app.core.config import get_settings
from app.models.schemas import ObjectClass

# ZERO에 보낼 프롬프트 목록. "helmet" 단독으로는 ZERO가 거의 못 잡아서(2026-08-02 실측)
# "safety helmet"을 쓴다.
_ZERO_TEXT_PROMPTS = ["person", "safety helmet", "vest"]

# 탐지 결과 class_name → 우리 클래스 매핑. "helmet"은 커스텀 배포 모델이 실제로 반환하는
# 이름이고, "safety helmet"은 ZERO 프롬프트용 별칭이다 — 커스텀 모델 응답엔 "safety
# helmet"이 아니라 "helmet"이 오므로 두 키 다 있어야 한다(2026-08-03: 이 매핑에
# "helmet"이 빠져 있어서 커스텀 모델의 헬멧 탐지 결과가 전부 무시되던 버그를 여기서 고쳤다).
_CLASS_NAME_TO_OBJECT_CLASS = {
    "person": ObjectClass.PERSON,
    "helmet": ObjectClass.HELMET,
    "safety helmet": ObjectClass.HELMET,
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


def _parse_detections(predictions) -> list[Detection]:
    detections: list[Detection] = []
    for p in predictions:
        class_name = p.class_name.lower()
        object_class = _CLASS_NAME_TO_OBJECT_CLASS.get(class_name)
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


def detect(frame: np.ndarray, confidence_threshold: float | None = None) -> list[Detection]:
    """단일 프레임(BGR numpy array, cv2로 읽은 형태)에서 person/helmet/vest를 탐지.

    confidence_threshold를 안 주면 0.3을 기본값으로 쓴다(커스텀 모델·ZERO 공통).
    2026-08-03 실측: v6-29k-capped는 helmet/vest는 0.3 근방에서도 잘 잡히지만, person은
    사람이 몇 명 안 겹치는 장면에선 0.5~0.9대로 잘 잡히다가도 사람이 여럿 붙어있는
    혼잡한 장면에서는 confidence=0.01(사실상 무필터)로 낮춰도 0.02~0.07대로 주저앉는
    경우가 있었다 — person 클래스가 helmet/vest보다 학습이 덜 된 것으로 보인다
    (development_log.md 참고 예정). 임계값을 더 낮춘다고 혼잡 장면의 person이 안정적으로
    잡히진 않으므로, 데모에서는 이 한계를 그대로 두고 있는 그대로 보여준다.
    """
    settings = get_settings()
    client = get_bdai_client()
    image_b64 = _encode_frame(frame)

    if settings.ppe_deployment_id:
        result = client.deployments.predict(
            settings.ppe_deployment_id,
            image_b64=image_b64,
            confidence=confidence_threshold if confidence_threshold is not None else 0.3,
        )
        return _parse_detections(result.predictions)

    result = client.foundation.predict(
        "zero",
        image={"image_b64": image_b64},
        text_prompts=_ZERO_TEXT_PROMPTS,
        confidence=confidence_threshold if confidence_threshold is not None else 0.3,
    )
    return _parse_detections(result.predictions)


# head/upper_body는 학습 클래스가 아니라(커스텀 모델은 no_vest/head를 직접 학습하므로
# 필요 없음) ZERO 전용 런타임 폴백 신호 — app.rules.ppe_compliance가 helmet/vest를 못
# 찾았을 때 "머리/상체는 보이는데 안전장비가 없다"를 확인해 미착용을 확정하는 데 쓴다.
# "head" 단독 프롬프트는 인식률이 0에 가깝다(실측) — "person head"/"upper body"로 바꾸면
# 잘 잡히는데(예: 6명 중 5~6명), "safety helmet"과 같은 호출에 섞으면 서로 경쟁해 인식률이
# 크게 떨어져(실측) detect()와는 별도 ZERO 호출로 분리했다.
def detect_head_upper_body(
    frame: np.ndarray, confidence_threshold: float | None = None
) -> tuple[list[tuple[float, float, float, float]], list[tuple[float, float, float, float]]]:
    """(head_boxes, upper_body_boxes)를 반환. 커스텀 모델(PPE_DEPLOYMENT_ID)이 설정된
    경우엔 이 폴백이 필요 없으므로 호출하지 않고 빈 리스트를 반환한다."""
    settings = get_settings()
    if settings.ppe_deployment_id:
        return [], []

    client = get_bdai_client()
    result = client.foundation.predict(
        "zero",
        image={"image_b64": _encode_frame(frame)},
        text_prompts=["person head", "upper body"],
        confidence=confidence_threshold if confidence_threshold is not None else 0.3,
    )
    heads, uppers = [], []
    for p in result.predictions:
        if p.geometry.type != "bbox":
            continue
        box = (p.geometry.x, p.geometry.y, p.geometry.x + p.geometry.w, p.geometry.y + p.geometry.h)
        if p.class_name == "person head":
            heads.append(box)
        elif p.class_name == "upper body":
            uppers.append(box)
    return heads, uppers
