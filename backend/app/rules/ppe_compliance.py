"""PPE(안전모·조끼) 착용 여부 판정 규칙 + 표시 안정화(히스테리시스).

2026-08-02 head 판정 폐기 → 재도입 경위:
  1) 원래 head+helmet IoU 기반 판정(논문 koreascience.kr, CFKO202419335085858)을 썼다.
  2) ZERO 프롬프트 "head" 단독은 인식률이 0에 가까워(실측) 한 번 폐기하고 "helmet/vest가
     안 잡히면 바로 미착용"으로 단순화했다.
  3) 그런데 실제 데모 영상에서 이 단순화가 오탐을 만들었다 — 사람이 멀거나(작게 보임)
     자세 때문에 각도가 안 좋으면 helmet/vest 자체가 실제로 착용했어도 안 잡히는데, 그걸
     곧장 "미착용"으로 확정해버렸다.
  4) 재실측 결과 "head"가 아니라 "person head"/"upper body"로 프롬프트를 바꾸면 인식이
     잘 된다(예: 6명 중 5~6명, confidence 0.4~0.6대) — "helmet"→"safety helmet"과 같은
     종류의 순수 어휘 문제였다. 다만 "safety helmet"과 같은 호출에 섞으면 서로 경쟁해
     인식률이 크게 떨어져(실측) app.inference.detector.detect_head_upper_body()가 별도
     ZERO 호출로 분리한다.

그래서 지금은 "helmet/vest가 안 잡히면 곧장 미착용"이 아니라, head/upper_body가 실제로
보이는데(=시야가 확보됐는데) 그 안에 helmet/vest가 없을 때만 미착용으로 확정한다. head/
upper_body조차 안 보이면(원거리·가림) 판단을 보류(UNKNOWN)한다 — False All-Clear 방지
원칙과 같은 방향이면서, 오탐도 줄인다.

표시 안정화(stabilize_display): 한 프레임의 순간 판정을 그대로 화면에 반영하면 오검출
한 번에 라벨이 깜빡인다. 같은 위치(position chaining, 추적 ID 없이)에서 **연속
confirm_count회(기본 2회) 같은 방향으로 나와야** 화면에 표시되는 상태가 바뀐다 — 미착용
쪽으로 갈 때도, 다시 착용으로 돌아올 때도 동일하게 적용한다(대칭 히스테리시스).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

BBox = tuple[float, float, float, float]  # x1, y1, x2, y2


class ComplianceState(StrEnum):
    WORN = "worn"
    NOT_WORN = "not_worn"
    UNKNOWN = "unknown"  # head/upper_body조차 안 보이거나(판단 보류), detect_helmet/vest가 꺼진 경우


@dataclass
class PpeCompliance:
    helmet: ComplianceState
    vest: ComplianceState


def _contains_ratio(inner: BBox, outer: BBox) -> float:
    """inner가 outer 안에 얼마나 포함되는지(교집합/inner 면적). person처럼 훨씬 큰
    박스 안에 head/vest 등 작은 박스가 들어있는지 볼 때는 IoU보다 이 지표가 적절하다
    (크기 차이가 크면 IoU는 항상 낮게 나와 포함 관계를 못 잡는다)."""
    ix1, iy1 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix2, iy2 = min(inner[2], outer[2]), min(inner[3], outer[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_inner = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
    return inter / area_inner if area_inner > 0 else 0.0


def _center_distance(a: BBox, b: BBox) -> float:
    """두 박스 중심점 사이 거리(px). 2026-08-02: 원래 IoU(겹침 비율)로 "같은 사람"을
    이었는데, 걷는 사람은 ~1초 샘플 사이에 박스가 거의 안 겹칠 만큼 이동해버려서 체이닝이
    자주 끊겼다(실측 — 확정된 위반이 30초 쿨다운 안에 또 새로 찍힘). situation_probe.py가
    이미 쓰는 중심점 거리 매칭으로 바꾸면 걸음 정도의 이동에는 완만하게 반응해 훨씬
    안정적이다."""
    acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bcx, bcy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5


def _adaptive_match_distance(person_box: BBox, cap_px: float) -> float:
    """고정 150px는 situation_probe(전신 매칭용)에서 그대로 가져온 값이라 사람들이 다닥다닥
    붙어 있으면(실측: 화면상 12px 간격) 옆 사람 스트림을 훔쳐가는 문제가 있었다. 사람 박스
    너비에 비례한 값을 쓰면 카메라에 가까워 보이는(박스가 큰) 사람은 더 넉넉하게, 작게
    보이는 사람은 더 빡빡하게 매칭돼 화면상 스케일에 맞게 반응한다."""
    width = max(1.0, person_box[2] - person_box[0])
    return min(cap_px, max(30.0, width * 0.75))


def evaluate_ppe_compliance(
    person_box: BBox,
    *,
    head_boxes: list[BBox] = (),
    helmet_boxes: list[BBox] = (),
    vest_boxes: list[BBox] = (),
    upper_body_boxes: list[BBox] = (),
    containment_threshold: float = 0.5,
    detect_helmet: bool = True,
    detect_vest: bool = True,
) -> PpeCompliance:
    """사람 한 명(person_box) 기준으로 헬멧/조끼 착용 여부를 판정한다.

    helmet: person_box 안에 helmet이 있으면 WORN. helmet은 없지만 head(시야 확보 신호)가
            있으면 NOT_WORN(머리는 보이는데 안전모가 없다는 뜻). head도 없으면(원거리·가림)
            UNKNOWN.
    vest:   같은 논리로 vest 유무 → upper_body(시야 확보 신호)로 폴백.

    2026-08-03 검토 후 폐기: helmet/vest 증거에 최소 신뢰도(예: 0.5)를 요구해 저신뢰도
    오탐(idx=36~38, confidence 0.33~0.45)을 걸러보려 했으나, 실측 결과 같은 사람의
    "진짜로 계속 착용 중인" 헬멧도 프레임마다 confidence가 0.35~0.85로 크게 흔들려서
    (idx=1~3만 봐도 0.39/0.35/0.46) 임계값을 걸면 오히려 멀쩡히 착용 중인 구간까지
    미착용으로 새로 오판시켰다 — 득보다 실이 커서 되돌렸다. 저신뢰도 오탐 억제는
    stabilize_display의 confirm_count(연속확정 횟수)로만 대응한다.
    """
    helmet_state = ComplianceState.UNKNOWN
    if detect_helmet:
        person_helmets = [h for h in helmet_boxes if _contains_ratio(h, person_box) >= containment_threshold]
        if person_helmets:
            helmet_state = ComplianceState.WORN
        else:
            person_heads = [h for h in head_boxes if _contains_ratio(h, person_box) >= containment_threshold]
            helmet_state = ComplianceState.NOT_WORN if person_heads else ComplianceState.UNKNOWN

    vest_state = ComplianceState.UNKNOWN
    if detect_vest:
        person_vests = [v for v in vest_boxes if _contains_ratio(v, person_box) >= containment_threshold]
        if person_vests:
            vest_state = ComplianceState.WORN
        else:
            person_uppers = [u for u in upper_body_boxes if _contains_ratio(u, person_box) >= containment_threshold]
            vest_state = ComplianceState.NOT_WORN if person_uppers else ComplianceState.UNKNOWN

    return PpeCompliance(helmet=helmet_state, vest=vest_state)


@dataclass
class _DisplayStream:
    zone: str | None
    ppe_type: str  # "helmet" | "vest"
    bbox_xyxy: BBox
    last_seen: datetime
    displayed_state: ComplianceState  # 지금 화면에 보여주고 있는(확정된) 상태
    pending_state: ComplianceState  # 이번 스트릭에서 나오고 있는 후보 상태
    pending_count: int


_display_streams: dict[str, list[_DisplayStream]] = {}  # camera_id -> 스트림들

_DEFAULT_MAX_GAP_SECONDS = 3.0
_DEFAULT_MATCH_DISTANCE_PX = 150.0  # app.inference.situation_probe와 같은 값(일관성)
# 2026-08-03: 2회였을 때 idx=15~16(가림으로 헬멧 탐지가 2프레임 연속 빠짐 → 착용인데
# 미착용 오판)처럼 짧은 흔들림도 그대로 확정돼버렸다. 3회로 늘리면 이런 2프레임짜리
# 흔들림은 흡수되고, 실제로 상태가 바뀐 경우엔 반영이 한 프레임(이 데모 기준 약 1초)
# 늦게 화면에 나타난다 — 반응 속도와 안정성의 트레이드오프.
_DEFAULT_CONFIRM_COUNT = 3


def reset_display_streams(camera_id: str | None = None) -> None:
    """2026-08-03: 이 모듈 전역 `_display_streams`는 프로세스가 살아있는 동안 계속 쌓이는데,
    `scenario_runner.reset()`(시나리오 재생 화면의 "초기화" 버튼)이 이걸 전혀 비우지
    않아서, 시나리오를 재시작해도 지난 재생에서 쌓인 스트림(연속 관측 횟수·확정 상태)이
    그대로 남아 다음 재생의 확정 타이밍에 영향을 줬다(실측 — 재생할 때마다 같은 사람의
    미착용 확정 시점이 조금씩 달라짐). camera_id를 안 주면 전체를 비운다."""
    if camera_id is None:
        _display_streams.clear()
    else:
        _display_streams.pop(camera_id, None)


def stabilize_display(
    camera_id: str,
    *,
    zone: str | None,
    ppe_type: str,
    raw_state: ComplianceState,
    bbox_xyxy: BBox,
    now: datetime,
    max_gap_seconds: float = _DEFAULT_MAX_GAP_SECONDS,
    match_distance_px: float = _DEFAULT_MATCH_DISTANCE_PX,
    confirm_count: int = _DEFAULT_CONFIRM_COUNT,
) -> ComplianceState:
    """순간 판정(raw_state)을 그대로 쓰지 않고, 같은 위치에서 연속 confirm_count회 같은
    방향으로 나와야 화면 표시 상태를 바꾼다 — WORN→NOT_WORN도, NOT_WORN→WORN도 동일하게
    2회 확인을 요구한다(대칭 히스테리시스).

    UNKNOWN 처리: 2026-08-03 실측 — 이전엔 raw_state==UNKNOWN이면 스트림을 건드리지 않고
    곧바로 UNKNOWN을 반환했는데, UNKNOWN은 위반 목록에 안 들어가니 "정상"과 화면상
    구분이 안 됐다. ZERO가 머리/헬멧 둘 다 놓치는 순간(가림·각도 등, 흔함)마다 확정된
    미착용 표시가 잠깐씩 "정상"처럼 깜빡이는 원인이었다. 이제는 근처에 이미 확정된
    스트림이 있으면 **그 표시 상태를 그대로 유지**한다 — "이번엔 정보가 없다"를 "방금
    확인됐다"로 덮어쓰지 않는다. pending_count는 건드리지 않아(노이즈 한 번으로 진행 중인
    스트릭을 깨지 않음) last_seen만 갱신해 스트림이 만료되지 않게 한다. 매칭되는 스트림이
    아예 없으면(첫 관측) 그때는 정말 UNKNOWN을 보여준다.

    위치 매칭은 app.rules.ppe_violation_log와 같은 방식이다 — 같은 zone·같은 ppe_type이고,
    이번 호출의 person_box 크기에 비례한 거리(match_distance_px는 그 상한) 이내이며,
    이번 순간(now)에 아직 다른 사람이 가져가지 않은 스트림 중 가장 가까운 것. "이번 순간에
    이미 다른 사람이 가져간 스트림 제외"는 한 프레임 안에서 다닥다닥 붙어 있는 두 사람이
    같은 스트림을 동시에 훔쳐가는 걸 막는다(실측: 인접한 두 사람 중 한 명만 진짜 미착용인데
    둘 다 그렇게 표시됨) — 직전 관측으로부터 max_gap_seconds 이내인지도 함께 본다."""
    streams = _display_streams.setdefault(camera_id, [])
    streams[:] = [s for s in streams if (now - s.last_seen).total_seconds() <= max_gap_seconds]

    adaptive_distance = _adaptive_match_distance(bbox_xyxy, match_distance_px)
    matched: _DisplayStream | None = None
    matched_dist = adaptive_distance
    for s in streams:
        if s.zone != zone or s.ppe_type != ppe_type or s.last_seen == now:
            continue  # last_seen==now: 이번 순간 이미 다른 사람이 가져간 스트림
        dist = _center_distance(s.bbox_xyxy, bbox_xyxy)
        if dist <= matched_dist:
            matched = s
            matched_dist = dist

    if raw_state == ComplianceState.UNKNOWN:
        if matched is None:
            return ComplianceState.UNKNOWN
        matched.bbox_xyxy = bbox_xyxy
        matched.last_seen = now
        return matched.displayed_state

    if matched is None:
        # 첫 관측도 곧바로 보여주지 않는다 — 새로 나타난 사람이든 기존 사람이든 동일하게
        # 연속 confirm_count회를 요구한다(대칭성). 확정 전까지는 UNKNOWN(판단 보류)으로 둔다.
        streams.append(
            _DisplayStream(
                zone=zone, ppe_type=ppe_type, bbox_xyxy=bbox_xyxy, last_seen=now,
                displayed_state=ComplianceState.UNKNOWN, pending_state=raw_state, pending_count=1,
            )
        )
        return ComplianceState.UNKNOWN

    matched.bbox_xyxy = bbox_xyxy
    matched.last_seen = now
    if raw_state == matched.pending_state:
        matched.pending_count += 1
    else:
        matched.pending_state = raw_state
        matched.pending_count = 1

    if matched.pending_count >= confirm_count:
        matched.displayed_state = matched.pending_state

    return matched.displayed_state
