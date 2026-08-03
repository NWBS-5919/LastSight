"""PPE(안전모·조끼) 미착용 감지 이력 저장·조회 (app/rules/fire_alert_log.py와 같은
카메라당 파일 하나 append-only 패턴).

2026-08-02: 평상시엔 추적(ByteTracker)을 아예 안 쓰기로 했다 — 사람이 화면을 들락날락할
때마다 추적 ID가 계속 새로 매겨져서(development_log.md 43번) ID 기반 "이미 기록한 위반인지"
판단이 원래도 완벽하지 않았는데, 이제는 애초에 ID 자체가 없다. 그래서 이 모듈은 "같은
구역에서, 최근 일정 시간 안에, 위치가 비슷하고 위반 항목 조합도 같은" 경우를 "계속되는 같은
위반"으로 보고 중복 기록하지 않는다(스페이셜+시간 기반 dedup) — 사람을 특정하지 않고
"위반 사건" 자체를 다룬다는 관점.

2026-08-02 개선: 처음엔 새로 들어온 위치를 "최근에 기록된 로그 항목"의 위치와만 비교했는데,
그 로그 항목은 최대 cooldown_seconds(기본 30초) 전 것일 수 있어 그 사이 사람이 걸어서
움직이면 IoU가 깨져 같은 위반이 여러 건으로 중복 기록될 수 있었다. 이제는 "위반이 계속되고
있다"는 상태를 카메라별 인메모리 스트림(_open_streams)으로 따로 들고, 매 호출마다 그 스트림의
"가장 최근에 본 위치"와 비교한다 — 감지 주기(~1초)마다 위치가 조금씩 갱신되므로 계속 걸어
다녀도 체이닝이 끊기지 않는다. 같은 스트림이 이어지는 동안은 로그에 딱 한 줄만 남긴다(2026-08-03
정정 — 예전엔 cooldown_seconds마다 재기록했는데, 그러면 한 사람의 한 위반이 여러 줄로 보여
혼란스러웠다). 서버 재시작 시 스트림은 초기화되지만(다른 인메모리 STATE와 동일한 트레이드오프),
영구 로그 파일 자체는 그대로 남는다.

2026-08-02 추가 개선: 그런데 실제로는 IoU도 걷는 사람에겐 자주 깨졌다 — 1초 사이 이동으로
박스가 거의 안 겹치면 "다른 사람"으로 오인해 30초 쿨다운 안에도 또 새로 기록됐다(실측:
2초 간격으로 같은 위반이 두 번 확정됨). app.inference.situation_probe가 이미 쓰는 **중심점
거리** 매칭으로 바꿨다 — 걸음 정도의 이동에는 IoU보다 훨씬 완만하게 반응한다.

2026-08-02 추가 후 정리: 한때 이 모듈 안에 "연속 2회 관측돼야 확정" 로직을 넣었었는데,
그 확인 책임을 app.rules.ppe_compliance.stabilize_display로 옮겼다(대칭 히스테리시스 —
미착용 확정도, 다시 착용으로 돌아오는 것도 연속 2회를 요구). 그래서 이 모듈이 받는
violations는 이미 안정화(확정)된 상태이고, 여기서는 원래 목적인 "같은 위반을 중복
기록하지 않는 것"만 담당한다.

2026-08-02 추가 개선: 고정 150px가 사람들이 다닥다닥 붙어 있는 장면(실측: 화면상 12px
간격)에서 옆 사람 스트림을 훔쳐가는 문제가 있었다 — 매칭 거리를 person_box 크기에 비례한
값으로 좁히고(app.rules.ppe_compliance._adaptive_match_distance와 동일 방식), 이번
순간(now)에 이미 다른 사람이 가져간 스트림은 제외하고 그중 가장 가까운 것만 매칭하도록
바꿨다 — 한 프레임 안에서 두 사람이 같은 스트림을 동시에 가져가는 걸 막는다.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.models.schemas import PpeViolationLogEntry

LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "ppe_violation_logs"

_DEFAULT_COOLDOWN_SECONDS = 30.0
_DEFAULT_MATCH_DISTANCE_PX = 150.0  # app.inference.situation_probe / app.rules.ppe_compliance와 같은 값

BBox = tuple[float, float, float, float]


@dataclass
class _OpenStream:
    """"같은 위반이 계속되고 있다"고 보는 진행 중인 위반 1건 — 사람이 아니라 위치를 잇는다."""

    zone: str | None
    violations: frozenset[str]
    bbox_xyxy: BBox
    last_seen: datetime


_open_streams: dict[str, list[_OpenStream]] = {}  # camera_id -> 진행 중인 위반 스트림들


def reset_streams(camera_id: str | None = None) -> None:
    """2026-08-03: `_open_streams`도 app.rules.ppe_compliance._display_streams와 같은 이유로
    scenario_runner.reset()에서 같이 비워야 한다 — 안 그러면 시나리오를 재생할 때마다
    지난 재생의 진행 중이던 위반 스트림이 새 재생에 이어붙어 dedup/쿨다운 타이밍이 달라진다.
    camera_id를 안 주면 전체를 비운다."""
    if camera_id is None:
        _open_streams.clear()
    else:
        _open_streams.pop(camera_id, None)


def _center_distance(a: BBox, b: BBox) -> float:
    acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bcx, bcy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5


def _adaptive_match_distance(person_box: BBox, cap_px: float) -> float:
    width = max(1.0, person_box[2] - person_box[0])
    return min(cap_px, max(30.0, width * 0.75))


def _log_path(camera_id: str) -> Path:
    return LOG_DIR / f"{camera_id}.json"


def load_ppe_violation_log(camera_id: str) -> list[PpeViolationLogEntry]:
    path = _log_path(camera_id)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [PpeViolationLogEntry.model_validate(v) for v in raw]


def _append(camera_id: str, entry: PpeViolationLogEntry) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = load_ppe_violation_log(camera_id)
    log.append(entry)
    _log_path(camera_id).write_text(
        json.dumps([e.model_dump() for e in log], ensure_ascii=False, indent=2), encoding="utf-8"
    )


def format_violation_text(violations: list[str]) -> str:
    """["helmet"] → "헬멧 미착용", ["helmet","vest"] → "헬멧, 조끼 미착용" 같은 조합 문구."""
    labels = {"helmet": "헬멧", "vest": "조끼"}
    names = [labels.get(v, v) for v in violations]
    return ", ".join(names) + " 미착용"


def record_if_new_violation(
    camera_id: str,
    *,
    zone: str | None,
    violations: list[str],
    now_iso: str,
    frame_path: str | None,
    bbox_xyxy: BBox | None,
    confidence: float | None,
    helmet_state: str | None = None,
    vest_state: str | None = None,
    cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
    match_distance_px: float = _DEFAULT_MATCH_DISTANCE_PX,
) -> PpeViolationLogEntry | None:
    """violations가 비어있으면 아무것도 안 한다(호출부는 이미 stabilize_display로 확정된
    위반만 넘길 것). 그렇지 않으면, 같은 구역·같은 위반 조합의 "진행 중인 스트림"
    (_open_streams) 중 가장 최근 위치와 중심점 거리가 match_distance_px 이내인 게 있으면
    같은 위반이 계속되는 것으로 보고 위치/최근 관측 시각만 갱신할 뿐, 다시 기록하지 않는다
    — 한 사람의 한 번의 위반은 로그에 한 줄만 남아야 한다. 매칭되는 스트림이 없으면(새
    위치, 새 조합, 또는 cooldown_seconds 넘게 안 보여 이미 정리된 스트림) 새 스트림을
    시작하고 그때 한 번만 기록한다.

    2026-08-03 정정: 예전엔 매칭되는 스트림이 있어도 cooldown_seconds(기본 30초)마다
    "그래도 계속되고 있다"는 걸 알리려고 재기록했는데, 오히려 "같은 사람이 두 명인 것처럼
    보인다"는 혼란을 낳았다(실측 — 30초 넘게 서 있던 헬멧 미착용자 1명이 로그엔 2줄로
    남음). 그 의도(계속되는 위반임을 표시)는 로그 여러 줄이 아니라 다른 방식(예: 사고
    리플레이에서 첫 감지~마지막 확인 구간으로 표시)으로 다뤄야 한다 — 최소한 이 로그
    자체는 "위반 사건 하나 = 한 줄"을 지킨다.

    반환값은 실제로 새로 기록한 항목(PpeViolationLogEntry) — 새로 기록하지 않았으면(같은
    위반이 계속되는 중) None. 호출부(scenario_runner)가 "새로 감지된 위반"일 때만 카운터를
    올리거나 이벤트 피드·라이브 타임라인에 반영하는 데 쓴다."""
    if not violations:
        return None

    now = datetime.fromisoformat(now_iso)
    violation_set = frozenset(violations)
    streams = _open_streams.setdefault(camera_id, [])

    # cooldown_seconds 넘게 안 보인 스트림은 끝난 것으로 보고 정리 — "추적"이 아니라
    # "최근 위치 체이닝"이므로 오래된 스트림을 계속 붙들고 있을 이유가 없다.
    streams[:] = [s for s in streams if (now - s.last_seen).total_seconds() <= cooldown_seconds]

    matched: _OpenStream | None = None
    if bbox_xyxy is not None:
        adaptive_distance = _adaptive_match_distance(bbox_xyxy, match_distance_px)
        matched_dist = adaptive_distance
        for s in streams:
            if s.zone != zone or s.violations != violation_set or s.last_seen == now:
                continue  # last_seen==now: 이번 순간 이미 다른 사람이 가져간 스트림
            dist = _center_distance(s.bbox_xyxy, bbox_xyxy)
            if dist <= matched_dist:
                matched = s
                matched_dist = dist

    if matched is not None:
        matched.bbox_xyxy = bbox_xyxy
        matched.last_seen = now
        return None  # 같은 스트림(위반이 계속되는 중) — 이미 한 번 기록했으니 다시 기록 안 함

    streams.append(
        _OpenStream(
            zone=zone,
            violations=violation_set,
            bbox_xyxy=bbox_xyxy if bbox_xyxy is not None else (0.0, 0.0, 0.0, 0.0),
            last_seen=now,
        )
    )

    entry = PpeViolationLogEntry(
        id=uuid.uuid4().hex,
        violations=violations,
        zone=zone,
        at=now_iso,
        frame_path=frame_path,
        bbox_xyxy=bbox_xyxy,
        confidence=confidence,
        helmet_state=helmet_state,
        vest_state=vest_state,
    )
    _append(camera_id, entry)
    return entry


def update_violation_review(
    camera_id: str,
    entry_id: str,
    *,
    reviewed_helmet: str | None,
    reviewed_vest: str | None,
    reviewed_at: str,
) -> PpeViolationLogEntry | None:
    """관리자가 카드에서 안전모/안전조끼 최종 판정을 확정 제출한다 — 원본 AI 판정
    (helmet_state/vest_state)은 지우지 않고, reviewed_* 필드에 별도로 남긴다(감사 추적).
    entry_id를 못 찾으면 None."""
    log = load_ppe_violation_log(camera_id)
    for i, e in enumerate(log):
        if e.id == entry_id:
            updated = e.model_copy(
                update={"reviewed_helmet": reviewed_helmet, "reviewed_vest": reviewed_vest, "reviewed_at": reviewed_at}
            )
            log[i] = updated
            _log_path(camera_id).write_text(
                json.dumps([x.model_dump() for x in log], ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return updated
    return None


def merge_violations(camera_id: str, id_a: str, id_b: str) -> PpeViolationLogEntry | None:
    """관리자가 타임라인에서 노드 하나를 다른 노드 위로 끌어다 놓아, "사실은 같은 사람의
    같은 위반이 위치 매칭 실패로 두 줄로 쪼개진 것"임을 직접 병합 확정한다(development_log.md
    참고 — 걷는 속도가 매칭 반경보다 빠르면 실제로 이런 중복이 생긴다).

    시각이 더 이른 쪽을 "원본"으로 남긴다 — 카드에 "가장 처음 감지된 이미지"가 보이도록
    frame_path/bbox_xyxy/confidence/violations/helmet_state/vest_state를 전부 이른 쪽
    기준으로 유지한다. 검토(reviewed_*) 기록은 둘 중 더 나중에 검토된 쪽을 살린다(둘 다
    검토 안 됐으면 미검토 그대로). 나중 쪽 항목은 로그에서 완전히 제거된다 — 병합은
    "둘이 사실 하나였다"는 사실 정정이라, 남겨봐야 다시 혼란을 준다.

    둘 중 하나라도 못 찾으면 None."""
    log = load_ppe_violation_log(camera_id)
    idx_a = next((i for i, e in enumerate(log) if e.id == id_a), None)
    idx_b = next((i for i, e in enumerate(log) if e.id == id_b), None)
    if idx_a is None or idx_b is None or idx_a == idx_b:
        return None

    entry_a, entry_b = log[idx_a], log[idx_b]
    earlier, later = (entry_a, entry_b) if entry_a.at <= entry_b.at else (entry_b, entry_a)

    merged_reviewed = earlier
    if later.reviewed_at is not None and (earlier.reviewed_at is None or later.reviewed_at > earlier.reviewed_at):
        merged_reviewed = earlier.model_copy(
            update={
                "reviewed_at": later.reviewed_at,
                "reviewed_helmet": later.reviewed_helmet,
                "reviewed_vest": later.reviewed_vest,
            }
        )

    new_log = [e for e in log if e.id not in (id_a, id_b)]
    new_log.append(merged_reviewed)
    new_log.sort(key=lambda e: e.at)
    _log_path(camera_id).write_text(json.dumps([x.model_dump() for x in new_log], ensure_ascii=False, indent=2), encoding="utf-8")
    return merged_reviewed
