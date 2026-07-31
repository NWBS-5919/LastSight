"""결정적 순간에만 ZERO를 한 번 더 불러 상황을 짧게 요약하는 2차 확인.

평소 상시 감지(person/helmet/vest, fire/smoke)는 가벼운 배포 모델/ZERO 단일 프롬프트로
처리하고, "화재경보 후 장기체류(PROLONGED_PRESENCE)"나 "관리구역 이상(ABNORMAL)"처럼
진짜 확인이 필요한 전환 순간에만 이 모듈을 불러 우려되는 상황 문구 여러 개를 ZERO에
동시에 묻는다. ZERO는 자유 텍스트 설명(캡셔닝)을 만들어주는 VLM이 아니라 개방형
어휘(open-vocabulary) 탐지 모델이다(`client.foundation.list()`로 실제 확인함 — 이
테넌트에는 "zero" 하나만 등록돼 있고 별도 VLM 캡셔닝 엔드포인트는 없음). 그래서
"자유 문장 생성"이 아니라 "짧은 우려 문구들을 프롬프트로 던져서 걸린 것만 문장으로
조립"하는 방식으로 구현한다.

상시 감지(가볍고 안정적) → 결정적 순간에만 추가 확인(정밀하지만 비용이 드는 것)이라는
이원화 구조 자체가 목적이라, 이 함수의 호출 실패는 전체 파이프라인을 막지 않는다 —
호출이 실패하면 situation_note는 그냥 None으로 남는다(경보 트리거 자체와 달리, 이 기능은
"있으면 좋은" 보조 정보이지 안전 판정의 필수 경로가 아니기 때문).
"""

from __future__ import annotations

import base64
import logging

import cv2
import numpy as np

from app.core.bdai_client import get_bdai_client

logger = logging.getLogger(__name__)

# 작업자가 화재경보 후 오래 관측될 때 확인하고 싶은 우려 상황들.
PROLONGED_PRESENCE_PROMPTS = ["쓰러진 사람", "바닥에 누워있는 사람", "연기에 둘러싸인 사람"]

# 관리구역 종류별로 확인하고 싶은 우려 상황들 (같은 변화감지 결과라도 종류에 따라 원인 문구가 다름).
CLEARANCE_ZONE_PROMPTS: dict[str, list[str]] = {
    "fire_extinguisher": ["소화기를 가리는 박스", "쌓여있는 적재물", "소화기 앞을 막은 물건"],
    "electrical_panel": ["가려진 전기패널", "전기패널 앞에 쌓인 물건"],
    "emergency_exit": ["막힌 비상구", "비상구 앞에 쌓인 물건", "닫힌 문"],
}

_DEFAULT_CONFIDENCE = 0.35


def _encode_frame(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("프레임을 JPEG로 인코딩하지 못했습니다.")
    return base64.b64encode(buf).decode("ascii")


def probe_situation(frame: np.ndarray, concern_prompts: list[str], *, confidence: float = _DEFAULT_CONFIDENCE) -> str | None:
    """프레임 한 장을 ZERO에 concern_prompts로 동시에 물어, 걸린 문구들로 짧은 문장을 만든다.

    걸린 게 하나도 없으면 None(굳이 "이상 없음"이라고 단정하지 않음 — 이 확인은 보조
    정보일 뿐, ZERO가 못 찾았다고 실제로 없다는 뜻은 아니기 때문). 호출 자체가 실패해도
    None을 반환하고 예외를 밖으로 던지지 않는다(호출부 파이프라인을 막지 않기 위함).
    """
    try:
        client = get_bdai_client()
        result = client.foundation.predict(
            "zero",
            image={"image_b64": _encode_frame(frame)},
            text_prompts=concern_prompts,
            confidence=confidence,
        )
    except Exception:
        logger.warning("situation_probe: ZERO 호출 실패", exc_info=True)
        return None

    hit_labels = sorted({p.class_name for p in result.predictions if p.class_name in concern_prompts})
    if not hit_labels:
        return None
    return "2차 확인(ZERO) 결과 우려 요소 발견: " + ", ".join(hit_labels)
