"""PPE(안전모·조끼) 착용 여부 판정 규칙.

development_log.md 33·36번 참고: helmet/vest 신호가 색상에 편향돼 있어(vest 66.8%가
파랑) "helmet 클래스가 잡혔으니까 착용"이라는 단순 판정은 색상 지름길 학습에 취약하다.
사용자가 공유한 논문(koreascience.kr, CFKO202419335085858)에서 제안한 head+helmet IoU
기반 판정을 따른다 — head(사람 머리, 안전모 유무와 무관하게 식별)와 helmet(안전모)을
각각 별도 클래스로 탐지한 뒤, 두 박스의 IoU가 임계값(기본 0.5, 논문 기준) 이상이면
"착용"으로 판정한다. 색을 보는 게 아니라 "안전모 모양의 물체가 머리 위치에 실제로
있는가"를 기하학적으로 확인하는 방식이라 색상 편향에 덜 취약하다.

no_vest 직접 클래스(CLAUDE.md 4-1 2026-07-30 추가)는 보조 신호로 같이 쓴다. vest는
head 같은 "짝이 되는 신체 부위" 클래스가 없어 IoU 방식이 아니라 person 박스와의 포함
관계로 직접 판정한다.

no_helmet 클래스는 뺐다 — SHWD(강의실 군중 데이터) 반입 후 no_helmet 라벨이 69,227개로
쏠려 클래스 불균형을 만들었고, 애초에 head+helmet IoU만으로 기하학적 판정이 가능해
직접 클래스가 없어도 helmet 판정 자체는 그대로 동작한다(development_log.md 참고). 다만
head가 아예 안 잡힌 경우(가림 등)에는 이제 helmet 미착용을 확정할 근거가 없어 UNKNOWN으로
남는다 — vest처럼 "직접 미착용 신호"가 없는 셈이라, False All-Clear보다는 판단 보류를
택한 것과 같은 방향이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

BBox = tuple[float, float, float, float]  # x1, y1, x2, y2


class ComplianceState(StrEnum):
    WORN = "worn"
    NOT_WORN = "not_worn"
    UNKNOWN = "unknown"  # 판단 근거(머리/몸통 등)가 애초에 안 잡힘 — 착용/미착용 모두 단정하지 않음


@dataclass
class PpeCompliance:
    helmet: ComplianceState
    vest: ComplianceState
    helmet_iou: float | None = None  # helmet 판정에 쓰인 head-helmet 최대 IoU (head가 잡혔을 때만 값 존재)


def _iou(a: BBox, b: BBox) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _contains_ratio(inner: BBox, outer: BBox) -> float:
    """inner가 outer 안에 얼마나 포함되는지(교집합/inner 면적). person처럼 훨씬 큰
    박스 안에 head/vest 등 작은 박스가 들어있는지 볼 때는 IoU보다 이 지표가 적절하다
    (크기 차이가 크면 IoU는 항상 낮게 나와 포함 관계를 못 잡는다)."""
    ix1, iy1 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix2, iy2 = min(inner[2], outer[2]), min(inner[3], outer[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_inner = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
    return inter / area_inner if area_inner > 0 else 0.0


def evaluate_ppe_compliance(
    person_box: BBox,
    *,
    head_boxes: list[BBox] = (),
    helmet_boxes: list[BBox] = (),
    vest_boxes: list[BBox] = (),
    no_vest_boxes: list[BBox] = (),
    helmet_iou_threshold: float = 0.5,
    containment_threshold: float = 0.5,
) -> PpeCompliance:
    """사람 한 명(person_box) 기준으로 헬멧/조끼 착용 여부를 판정한다.

    helmet: head 박스가 있으면 helmet과의 IoU로 우선 판정(색상 무관, 기하학적 판정).
            head가 없으면 helmet 직접 신호로만 착용 여부를 보조 판정(미착용 확정 근거는
            없음 — no_helmet 클래스를 빼서, head가 안 잡히면 UNKNOWN으로 판단을 보류한다).
    vest:   person 영역 안에 있는 vest/no_vest 직접 신호로 판정.
    """
    person_heads = [h for h in head_boxes if _contains_ratio(h, person_box) >= containment_threshold]
    person_helmets = [h for h in helmet_boxes if _contains_ratio(h, person_box) >= containment_threshold]

    helmet_state = ComplianceState.UNKNOWN
    helmet_iou: float | None = None
    if person_heads:
        best_iou = 0.0
        for head in person_heads:
            for helmet in person_helmets:
                best_iou = max(best_iou, _iou(head, helmet))
        helmet_iou = best_iou
        helmet_state = ComplianceState.WORN if best_iou >= helmet_iou_threshold else ComplianceState.NOT_WORN
    elif person_helmets:
        helmet_state = ComplianceState.WORN

    person_vests = [v for v in vest_boxes if _contains_ratio(v, person_box) >= containment_threshold]
    person_no_vests = [v for v in no_vest_boxes if _contains_ratio(v, person_box) >= containment_threshold]

    if person_vests and not person_no_vests:
        vest_state = ComplianceState.WORN
    elif person_no_vests and not person_vests:
        vest_state = ComplianceState.NOT_WORN
    elif person_vests and person_no_vests:
        # 상충하는 신호 — False All-Clear(착용했다고 잘못 판단)가 미착용을 놓치는 것보다
        # 더 위험한 오류라는 절대 원칙(CLAUDE.md 2번)과 같은 방향으로, 미착용 쪽을 우선한다.
        vest_state = ComplianceState.NOT_WORN
    else:
        vest_state = ComplianceState.UNKNOWN

    return PpeCompliance(helmet=helmet_state, vest=vest_state, helmet_iou=helmet_iou)
