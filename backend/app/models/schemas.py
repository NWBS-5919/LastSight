"""프로젝트 지침(CLAUDE.md 4번 섹션)의 라벨 정의를 코드에서 그대로 참조하기 위한 스키마.

클래스/속성/이벤트 라벨 이름을 여기 말고 다른 곳에서 새로 만들지 말 것 —
BDAI 플랫폼 스키마, 라벨링, 규칙 엔진, 대시보드 표시 문구가 전부 이 정의를 기준으로 맞춰져야 함.
"""

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class ObjectClass(StrEnum):
    PERSON = "person"
    HELMET = "helmet"
    VEST = "vest"
    FIRE = "fire"
    SMOKE = "smoke"
    # 2026-07-31: PPE 색상 편향 대응(CLAUDE.md 4-1 참고) — 직접 미착용 신호 학습용 보조 클래스.
    # no_helmet은 뺐다 — SHWD(강의실 군중 데이터) 반입 후 no_helmet 라벨이 69,227개로
    # 다른 클래스 대비 압도적으로 쏠려 클래스 불균형을 만들었고, 어차피 head+helmet IoU
    # 규칙(app/rules/ppe_compliance.py)이 기하학적으로 미착용을 판단할 수 있어 중복이었다.
    # vest는 head 같은 짝지을 신체 부위 클래스가 없어 no_vest를 그대로 유지한다
    # (없으면 "미착용 확정"을 할 방법이 없어짐).
    NO_VEST = "no_vest"
    HEAD = "head"


class HelmetColor(StrEnum):
    WHITE = "흰색"
    YELLOW = "노란색"
    RED = "빨간색"
    BLUE = "파란색"
    OTHER = "기타"
    UNCLEAR = "불명확"


class VestColor(StrEnum):
    YELLOW = "노란색"
    ORANGE = "주황색"
    OTHER = "기타"
    UNCLEAR = "불명확"


class VisibilityLevel(StrEnum):
    HIGH = "높음"
    MEDIUM = "중간"
    LOW = "낮음"


class WorkerEvent(StrEnum):
    """상태 규칙 엔진(app/rules/state_engine.py)의 출력값. 대시보드 표시 문구는 이 값에서 파생시킬 것.

    2026-07-30: 출구 가상선 통과 확인(EXIT_CROSSING/REENTRY/EVACUATED/EXIT_UNCONFIRMED) 방식을
    폐기했다 — CCTV가 문 바깥쪽까지 잡는 경우가 현실적으로 드물어 "통과 확인" 자체가 구조적으로
    성립하기 어려웠다(development_log.md 17번 참고). 대신 "출구를 통과했는지"를 판정하지 않고,
    화재경보 이후 "지금도 관측되고 있는가·얼마나 오래 관측되고 있는가"만 정직하게 보여주는
    방식으로 단순화했다 — AI가 대피 완료를 확정 선언하지 않는다는 절대 원칙과 더 잘 맞는다."""

    INSIDE_OBSERVED = "inside_observed"  # 현재 관측 중 (화재 미발생 또는 경보 후 임계시간 이내)
    PROLONGED_PRESENCE = "prolonged_presence"  # 화재경보 후 임계시간 넘도록 계속 관측됨 — 확인 필요
    TRACKING_LOST = "tracking_lost"  # 현재 관측 안 됨 (안전 여부 확정하지 않음, 마지막 위치만 제공)
    CAMERA_FAILURE = "camera_failure"


class WorkerStatus(BaseModel):
    """대시보드/구조카드에 노출되는 작업자 1명의 상태.

    주의: 이 시스템은 어떤 경우에도 "이 사람이 안전하게 대피했다"를 확정 선언하지 않는다
    (CLAUDE.md 2번 절대 원칙). TRACKING_LOST는 "더 이상 관측 안 됨"이라는 사실만 전달할 뿐,
    안전/위험 여부에 대한 판단을 포함하지 않는다 — 화면 밖으로 나간 이유(대피/사각지대/장애물
    뒤)를 AI가 추측하지 않는다.
    """

    track_id: str
    event: WorkerEvent
    first_seen_at: str | None = None  # ISO8601 — 이 track_id가 처음 감지된 시각(체류시간 계산용)
    last_zone: str | None = None
    last_seen_at: str | None = None  # ISO8601
    last_frame_path: str | None = None
    reference_frame_path: str | None = None
    reference_bbox_xyxy: tuple[float, float, float, float] | None = None  # reference_frame_path 이미지 안에서 이 사람 위치 — 한 프레임에 여러 명이 있을 때 누구인지 표시하는 용도
    helmet_color: HelmetColor | None = None
    vest_color: VestColor | None = None
    top_color: str | None = None
    visibility: VisibilityLevel | None = None
    confidence: float | None = None  # 마지막 관측 시점 person 탐지 신뢰도(0~1) — 추정치임을 드러내기 위한 보조 정보
    situation_note: str | None = None  # PROLONGED_PRESENCE 전환 시 ZERO 추가 확인 결과로 채워지는 짧은 상황 설명 (app/rules/situation_probe.py)
    priority_score: float | None = None  # 확인 우선순위 점수(0~100) — app/rules/triage.py, 요청 시점에 계산해 채움(저장값 아님)
    current_bbox_xyxy: tuple[float, float, float, float] | None = None  # 이번 프레임에 실제로 보일 때만 채워짐 — 프론트가 관측중(초록)/장기체류(빨강) 실시간 박스를 그리는 용도


class PersonComplianceBox(BaseModel):
    """평상시(추적 없음) 화면에서 사람 bbox 위에 "헬멧 착용"/"헬멧 미착용" 같은 라벨을
    실시간으로 그리기 위한 이번 프레임 스냅샷 1건. 화재 이후의 WorkerStatus와 달리
    track_id가 없다 — 평상시엔 추적 자체를 안 쓰므로(PpeViolationLogEntry와 동일한 이유,
    development_log.md 43·46번 참고), 매 프레임 새로 계산해서 그 순간만 보여주고 누적하지
    않는다. 위반이 새로 감지된 순간만 별도로 남기는 PpeViolationLogEntry(누적 로그)와
    역할이 다르다 — 이건 "지금 이 사람이 착용했는지" 실시간 표시용이다."""

    bbox_xyxy: tuple[float, float, float, float]
    zone: str | None = None
    helmet: str  # "worn" | "not_worn" | "unknown" (app/rules/ppe_compliance.ComplianceState 값 그대로)
    vest: str
    confidence: float | None = None


class WorkerEventLogEntry(BaseModel):
    """작업자 타임라인에 표시할 상태 변화 기록 1건. resolve_status()가 이전 상태 대비
    event가 실제로 바뀔 때만 이 로그를 추가한다(매 프레임 남기지 않음).

    2026-07-31 추가(frame_path/bbox_xyxy): 화면이 작고 복장이 통일된 CCTV 환경에서는
    사람이 사라졌다 나타나면 추적 ID가 바뀌는 걸 막을 수 없다는 게 확인됐다(development_log.md
    참고) — 그래서 "같은 ID로 이어 붙이기"를 시도하는 대신, 매 로그마다 그 순간의 증거 사진
    (프레임 경로 + 박스 좌표)을 같이 남겨서 관리자가 직접 눈으로 "같은 사람인지" 판단할 수
    있게 한다. ID가 바뀌어도 로그와 사진은 끊기지 않고 계속 쌓인다."""

    track_id: str
    event: WorkerEvent
    zone: str | None = None
    at: str  # ISO8601
    situation_note: str | None = None  # PROLONGED_PRESENCE 전환 시 ZERO 추가 확인 결과(app/rules/situation_probe.py)
    frame_path: str | None = None  # 이 로그가 기록된 순간의 프레임 이미지 URL/경로
    bbox_xyxy: tuple[float, float, float, float] | None = None  # frame_path 위에 그릴 사람 박스 좌표


class PpeViolationLogEntry(BaseModel):
    """PPE 미착용이 새로 감지된 순간 1건. 이미 미착용 상태가 계속되는 동안은 다시
    기록하지 않고, 새로운 미착용 상황(직전과 위치·시간이 다른)일 때만 기록한다.

    2026-08-02: 평상시엔 추적(ByteTracker) 자체를 안 쓰기로 했다 — 사람이 화면을
    들락날락할 때마다 추적 ID가 계속 새로 매겨져서(development_log.md 43번) ID 기반
    집계가 의미가 없었기 때문. 그래서 이 로그도 track_id가 아니라 **구역+시간+위치**로
    "같은 위반이 계속 이어지는 중인지"를 판단한다(app/rules/ppe_violation_log.py의
    스페이셜 dedup) — 사람을 특정하지 않고, 위반 "사건"만 기록한다는 관점.

    한 사람이 헬멧·조끼를 동시에 미착용이면 violations에 둘 다 담겨 한 줄로 기록된다
    (예: ["helmet", "vest"] → 화면엔 "헬멧, 조끼 미착용"으로 조합해서 보여줄 것).

    2026-08-03 추가: 관리자가 카드를 열어 AI 판정(helmet_state/vest_state)을 직접 검토·
    수정할 수 있게 됐다 — 수정 결과는 reviewed_* 필드에 별도로 남기고 원본 AI 판정은
    지우지 않는다(둘 다 착용으로 정정해도 "AI가 원래 뭐라고 봤는지"는 감사 추적으로 남음).
    reviewed_at이 None이면 아직 아무도 검토하지 않은 상태."""

    # 2026-08-03 정정: default_factory를 준 이유 — 이 필드를 추가하기 전부터 쌓여있던
    # 로그 파일(id 없음)을 불러올 때 필수 필드 누락으로 검증 예외가 나면서 run_scenario()
    # 태스크가 아무 로그도 없이 조용히 죽는 문제가 실측으로 확인됐다(예외를 아무도
    # await/조회하지 않는 백그라운드 태스크라 콘솔에도 안 남았다). 기존 항목은 매번 새
    # id를 받게 되지만(그 항목을 다시 검토·수정할 일은 없으므로 무해), 새로 생기는 항목은
    # 어차피 생성 시점에 명시적으로 id를 넘겨준다(app/rules/ppe_violation_log.py).
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)  # 관리자가 이 항목을 특정해 검토(수정)할 때 쓰는 고유 식별자
    violations: list[str]  # "helmet"/"vest" 중 이번에 미착용으로 감지된 항목들(1개 이상)
    zone: str | None = None
    at: str  # ISO8601
    frame_path: str | None = None
    bbox_xyxy: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    helmet_state: str | None = None  # AI 원판정: "worn"/"not_worn"/"unknown"
    vest_state: str | None = None
    reviewed_at: str | None = None  # 관리자가 검토를 제출한 시각(ISO8601) — None이면 미검토
    reviewed_helmet: str | None = None  # 관리자가 최종 확정한 값 — None이면 AI 판정 그대로 유지
    reviewed_vest: str | None = None


class PpeDetectionSettings(BaseModel):
    """카메라별로 헬멧/조끼 미착용 감지를 각각 켜고 끌 수 있는 설정.

    예: 어떤 현장은 조끼 규정이 없어서 조끼 감지는 끄고 헬멧만 보고 싶을 수 있다.
    꺼진 항목은 app/rules/ppe_compliance.py에서 아예 판정을 안 하고(UNKNOWN 취급),
    위반 로그도 생기지 않는다."""

    camera_id: str
    detect_helmet: bool = True
    detect_vest: bool = True


class ClearanceZoneLogEntry(BaseModel):
    """관리구역 상태 변화 기록 1건 (WorkerEventLogEntry와 같은 패턴).
    evaluate_clearance_zone()이 계산한 새 상태가 직전과 다를 때만 한 줄 남긴다."""

    zone_id: str
    state: "ClearanceZoneState"
    at: str  # ISO8601
    situation_note: str | None = None  # ABNORMAL 전환 시 ZERO 추가 확인 결과(app/rules/situation_probe.py)


class IncidentTimelineEntry(BaseModel):
    """사고 리플레이 타임라인 한 줄 — 화재경보/작업자 상태변화/관리구역 상태변화/PPE
    미착용/구역별 상황집계를 한 종류(source)로 통합해 시간순으로 병합한 것.
    app/api/incidents.py에서 조립한다.

    track_id는 source="worker"(비상시에만 추적하므로 track_id가 있음)일 때만 채워진다 —
    "ppe_violation"/"zone_situation"은 평상시·구역집계 성격상 특정 사람 ID를 안 쓴다."""

    at: str  # ISO8601
    source: str  # "fire_alert" | "worker" | "clearance_zone" | "ppe_violation" | "zone_situation"
    text: str  # 대시보드에 그대로 표시할 한 줄(또는 여러 줄) 설명
    track_id: str | None = None
    zone_id: str | None = None
    situation_note: str | None = None
    frame_path: str | None = None  # 클릭하면 이 순간의 증거 사진을 보여주기 위한 경로
    bbox_xyxy: tuple[float, float, float, float] | None = None


class AlarmSource(StrEnum):
    AUTO_DETECTION = "auto_detection"  # app/rules/alarm_trigger.py 가 fire/smoke 탐지로 자동 발생
    MANUAL = "manual"  # 관리자가 수동으로 입력 (보조 오버라이드)


class FireAlert(BaseModel):
    """화재경보 1건. person 추적·상태 규칙 엔진은 이 이벤트가 발생한 이후부터 동작한다."""

    camera_id: str
    zone_id: str | None = None
    triggered_at: str  # ISO8601
    source: AlarmSource
    confidence: float | None = None  # source가 AUTO_DETECTION일 때 fire/smoke 탐지 신뢰도


class ZoneSituationBox(BaseModel):
    """구역 집계 캡처 사진(frame_path) 위에 그릴 사람 1명의 박스. category는 breakdown의
    key와 같은 값을 쓴다("체류중"/"쓰러진 사람"/"연기에 둘러싸인 사람") — 그래서 로그를
    열어봤을 때 사진 위에 "이 사람이 쓰러진 사람이다"처럼 카테고리별로 색을 다르게 그릴 수
    있다. 개인 식별자(track_id)는 담지 않는다 — 이 로그는 "그 순간 전체 상황"을 남기는
    용도이지 특정 개인을 추적하는 용도가 아니다."""

    category: str
    bbox_xyxy: tuple[float, float, float, float]


class ZoneSituationEntry(BaseModel):
    """구역 하나의 상황 집계 1건 — 그 구역에 지금 몇 명이 있고, 그중 몇 명이 어떤
    우려 상황(situation_probe.PROLONGED_PRESENCE_PROMPTS)에 해당하는지.

    breakdown의 key는 situation_probe의 프롬프트 문구를 그대로 쓰거나("쓰러진 사람" 등),
    특별한 우려 신호가 없는 사람은 "체류중"으로 묶는다. total은 항상
    sum(breakdown.values())와 같다 — ZERO가 찾은 박스를 그 구역에서 추적 중인 사람과
    위치로 매칭해서 정확히 한 카테고리에만 속하도록 만들기 때문(app/inference/situation_probe.py
    의 probe_zone_situation 참고). boxes는 breakdown과 같은 인원을 1명씩 박스로 풀어놓은
    것이라 항상 len(boxes) == total이다 — 캡처 이미지(frame_path) 위에 카테고리별 박스를
    그리는 데 쓴다."""

    zone_id: str
    total: int
    breakdown: dict[str, int]  # 예: {"체류중": 1, "쓰러진 사람": 3, "연기에 둘러싸인 사람": 1}
    boxes: list[ZoneSituationBox] = []


class ZoneSituationLogEntry(BaseModel):
    """장기체류(PROLONGED_PRESENCE) 전환이 하나라도 생길 때마다 그 순간 전체 구역을
    다시 집계해서 남기는 로그 1건. 개인별 situation_note와 별개로, "지금 전체적으로
    어떤 상황인지"를 관리자가 한눈에 보기 위한 것."""

    camera_id: str
    at: str  # ISO8601
    zones: list[ZoneSituationEntry]
    frame_path: str | None = None  # 이 집계에 쓰인 프레임 — 클릭하면 전체 장면 사진을 보여줌


Point = tuple[float, float]


class ZoneDef(BaseModel):
    zone_id: str
    polygon: list[Point]  # >= 3점, 카메라 원본 해상도 기준 픽셀 좌표


class ZoneMapConfig(BaseModel):
    camera_id: str
    image_width: int | None = None
    image_height: int | None = None
    zones: list[ZoneDef] = []
    clearance_zones: list["ClearanceZoneDef"] = []


class ClearanceZoneType(StrEnum):
    """평상시 예방 축 — '이 구역이 기준 화면(등록 시점 사진)과 달라졌는지'를 감시하는 구역 종류.

    셋 다 판정 방식(app/rules/clearance_zone.py의 변화 감지)이 완전히 같다 — 종류는 UI 표시·
    라벨링 용도로만 구분한다. 소화기도 별도로 "소화기 클래스"를 탐지하는 모델을 학습시키는
    대신 이 방식으로 처리한다: 실제 CCTV 환경(높은 각도로 작게, 비스듬히 찍히고, 공사현장
    특성상 사람·자재가 계속 오가는 환경)에서는 공개 데이터셋(대부분 정면/눈높이 사진)으로
    학습한 탐지 모델이 각도 차이 때문에 잘 안 맞을 위험이 크고, 어차피 "그 자리가 가려졌는지"만
    확인하면 되므로 변화 감지만으로 충분하다.

    스프링클러/화재감지기 주변 적재 높이 위반은 후보로 검토했으나 제외했다 — 일반적인 CCTV는
    사람·바닥 영역 위주로 비스듬히 아래를 보게 설치돼 천장 근처가 화각에 안 잡히는 경우가
    많고, 카메라를 새로 달거나 재배치하지 않는다는 전제(기존 CCTV 그대로 활용)와도 안 맞는다."""

    FIRE_EXTINGUISHER = "fire_extinguisher"
    ELECTRICAL_PANEL = "electrical_panel"
    EMERGENCY_EXIT = "emergency_exit"


class ClearanceZoneDef(BaseModel):
    zone_id: str
    zone_type: ClearanceZoneType
    polygon: list[Point]  # >= 3점, 카메라 원본 해상도 기준 픽셀 좌표
    label: str | None = None  # 관리자가 붙이는 설명 (예: "배전반 A")
    baseline_frame_path: str | None = None  # "지금 상태를 기준으로 저장" 시점의 참조 이미지


class ClearanceZoneState(StrEnum):
    NORMAL = "normal"
    OBSERVING = "observing"  # 변화가 감지됐지만 지속시간 기준을 아직 못 채움
    ABNORMAL = "abnormal"  # 지속시간 기준을 채워 이상으로 확정됨
    CAMERA_FAILURE = "camera_failure"


class ClearanceZoneStatus(BaseModel):
    zone_id: str
    state: ClearanceZoneState
    changed_since: str | None = None  # ISO8601, 변화가 처음 관측된 시각 (state != NORMAL일 때)
    last_checked_at: str | None = None  # ISO8601
    last_frame_path: str | None = None
    situation_note: str | None = None  # ABNORMAL 전환 시 ZERO 추가 확인 결과(app/rules/situation_probe.py)


class SituationSummary(BaseModel):
    """상황 타임라인의 "요약 브리핑" 버튼 결과 — 이 시점까지 시스템이 실제로 기록한
    데이터(화재경보, 구역별 인원, 2차 확인 이력, PPE 위반)를 근거로 Gemini가 작성한 한국어
    요약. 어디까지나 보조 정보이며(disclaimer), 절대 원칙(CLAUDE.md 2번)을 위반하는 문장이
    나오지 않도록 프롬프트에서 강제한다 — 전원 안전/대피 완료 확정, 잔류인원 확정 금지.

    2026-08-04: 문단 하나로 된 줄글은 관리자가 급하게 훑어보기 어렵다는 피드백으로,
    한 줄 headline + 짧은 문장 여러 개(points)로 구조화해서 돌려준다 — 프론트엔드가
    카드/불릿 형태로 그리기 쉽게."""

    headline: str
    points: list[str]
    generated_at: str  # ISO8601
    disclaimer: str = "이 요약은 AI가 자동 생성한 추정 정보이며, 관리자 판단을 대체하지 않습니다."
