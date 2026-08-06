"""결정적 순간에만 ZERO를 한 번 더 불러 상황을 짧게 요약하는 2차 확인.

평소 상시 감지(person/helmet/vest, fire/smoke)는 가벼운 배포 모델/ZERO 단일 프롬프트로
처리하고, 화재경보 이후 매초 재확인처럼 진짜 확인이 필요한 순간에만 이 모듈을 불러
우려되는 상황 문구 여러 개를 ZERO에 동시에 묻는다. ZERO는 자유 텍스트 설명(캡셔닝)을
만들어주는 VLM이 아니라 개방형
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
# 2026-08-02: "바닥에 누워있는 사람"은 "쓰러진 사람"과 사실상 같은 모습이라(ZERO 입장에서도
# 거의 항상 같이 걸리거나 같이 안 걸림) 중복이었다 — 구역별 집계 로그(probe_zone_situation)의
# 카테고리 예시(쓰러짐/연기에 갇힘 2종)에 맞춰 정리했다.
PROLONGED_PRESENCE_PROMPTS = ["쓰러진 사람", "연기에 둘러싸인 사람"]

# ZERO는 한글 프롬프트를 사실상 인식하지 못한다(2026-08-02 실측: LastSight_Demo.mp4 프레임에서
# "사람"/"쓰러진 사람"은 항상 0건인데 "person"/"fallen person"은 정상 인식 — 어휘가 영어
# 위주). 그래서 위 한글 문구(카테고리명, CLAUDE.md 4-3에 정의된 고정 값)는 API·로그에 그대로
# 쓰되, ZERO에 실제로 보내는 프롬프트만 검증된 영어로 바꿔치기하고 결과를 다시 한글로 매핑한다.
# "쓰러진 사람"/"person"류는 실측 확인(0.4~0.58).
_KOREAN_TO_ZERO_PROMPT: dict[str, str] = {
    "쓰러진 사람": "fallen person",
    "연기에 둘러싸인 사람": "distressed person in smoke",
}


def _to_zero_prompts(korean_prompts: list[str]) -> tuple[list[str], dict[str, str]]:
    """한글 우려 문구 목록을 ZERO가 인식하는 영어 프롬프트로 바꾼다.

    반환값: (ZERO에 보낼 영어 프롬프트 목록, {영어 응답 class_name: 원래 한글 문구} 역매핑).
    매핑에 없는 문구는 번역 없이 그대로 보낸다(새 문구 추가 시 매핑 누락돼도 조용히 깨지지
    않고 예전처럼 동작 — 다만 그 경우 한글이라 다시 0건이 나올 수 있다는 점을 감안할 것).
    """
    english = [_KOREAN_TO_ZERO_PROMPT.get(p, p) for p in korean_prompts]
    reverse = {en: ko for ko, en in zip(korean_prompts, english)}
    return english, reverse


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
    zero_prompts, reverse = _to_zero_prompts(concern_prompts)
    try:
        client = get_bdai_client()
        result = client.foundation.predict(
            "zero",
            image={"image_b64": _encode_frame(frame)},
            text_prompts=zero_prompts,
            confidence=confidence,
        )
    except Exception:
        logger.warning("situation_probe: ZERO 호출 실패", exc_info=True)
        return None

    hit_labels = sorted({reverse[p.class_name] for p in result.predictions if p.class_name in reverse})
    if not hit_labels:
        return None
    return "2차 확인(ZERO) 결과 우려 요소 발견: " + ", ".join(hit_labels)


BBox = tuple[float, float, float, float]

STAY_CATEGORY = "체류중"  # ZERO가 찾은 어떤 우려 카테고리에도 안 걸린 사람의 기본 분류
_DEFAULT_MATCH_DISTANCE_PX = 150.0  # ZERO가 찾은 박스를 이 거리(픽셀) 안의 가장 가까운 추적 인원에만 매칭


def probe_zone_situation(
    frame: np.ndarray,
    workers_by_zone: dict[str, list[tuple[str, BBox]]],
    *,
    prompts: list[str] | None = None,
    confidence: float = _DEFAULT_CONFIDENCE,
    match_distance_px: float = _DEFAULT_MATCH_DISTANCE_PX,
) -> tuple[dict[str, dict[str, int]], dict[str, str]]:
    """프레임 전체를 ZERO에 한 번만 물어, 찾은 우려 상황 박스를 **그 순간 추적 중인 사람들과
    위치(중심점 거리)로 매칭**해서 구역별로 정확히 집계한다 — "쓰러진 사람" 박스가 우리가
    이미 추적하는 몇 번째 사람인지 코드로 알 방법이 없다는 문제를, 위치 매칭으로 해결한다.

    workers_by_zone: {zone_id: [(track_id, bbox_xyxy), ...]} — 지금 이 프레임에 실제로
    보이는 사람만 넘길 것(tracking_lost는 애초에 bbox가 없으므로 자연히 제외됨).

    반환값:
      - breakdown: {zone_id: {"체류중": N, "쓰러진 사람": M, ...}} — 항상
        sum(breakdown[zone].values()) == len(workers_by_zone[zone])가 성립한다
        (매칭 안 된 사람은 전부 STAY_CATEGORY로 남기 때문).
      - matched_category: {track_id: category} — 호출부가 각 작업자의 situation_note를
        채우는 데 쓴다(zone_situation_log와 개인별 situation_note를 같은 결과로 동기화).

    ZERO 호출이 실패해도 예외를 던지지 않는다 — 이 경우 전원 STAY_CATEGORY로만 채워진
    breakdown을 반환한다(장기체류 집계 로그 자체는 계속 남겨야 하므로, situation_probe
    실패가 로그 생성 자체를 막으면 안 된다).
    """
    prompts = prompts or PROLONGED_PRESENCE_PROMPTS

    breakdown: dict[str, dict[str, int]] = {zone_id: {STAY_CATEGORY: len(members)} for zone_id, members in workers_by_zone.items()}
    matched_category: dict[str, str] = {}

    all_workers = [(zone_id, tid, bbox) for zone_id, members in workers_by_zone.items() for tid, bbox in members]
    if not all_workers:
        return breakdown, matched_category

    zero_prompts, reverse = _to_zero_prompts(prompts)
    try:
        client = get_bdai_client()
        result = client.foundation.predict(
            "zero",
            image={"image_b64": _encode_frame(frame)},
            text_prompts=zero_prompts,
            confidence=confidence,
        )
    except Exception:
        logger.warning("situation_probe: 구역 집계용 ZERO 호출 실패", exc_info=True)
        return breakdown, matched_category

    for pred in result.predictions:
        korean_label = reverse.get(pred.class_name)
        if korean_label is None or pred.geometry.type != "bbox":
            continue
        px, py = pred.geometry.x + pred.geometry.w / 2, pred.geometry.y + pred.geometry.h / 2

        best: tuple[str, str] | None = None
        best_dist = match_distance_px
        for zone_id, tid, bbox in all_workers:
            if tid in matched_category:
                continue  # 이미 다른 카테고리로 확정된 사람은 다시 매칭하지 않음(중복 방지)
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = (zone_id, tid)

        if best is not None:
            zone_id, tid = best
            breakdown[zone_id][STAY_CATEGORY] -= 1
            breakdown[zone_id][korean_label] = breakdown[zone_id].get(korean_label, 0) + 1
            matched_category[tid] = korean_label

    return breakdown, matched_category
