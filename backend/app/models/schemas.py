"""프로젝트 지침(CLAUDE.md 4번 섹션)의 라벨 정의를 코드에서 그대로 참조하기 위한 스키마.

클래스/속성/이벤트 라벨 이름을 여기 말고 다른 곳에서 새로 만들지 말 것 —
BDAI 플랫폼 스키마, 라벨링, 규칙 엔진, 대시보드 표시 문구가 전부 이 정의를 기준으로 맞춰져야 함.
"""

from enum import StrEnum

from pydantic import BaseModel


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
    last_zone: str | None = None
    last_seen_at: str | None = None  # ISO8601
    last_frame_path: str | None = None
    reference_frame_path: str | None = None
    helmet_color: HelmetColor | None = None
    vest_color: VestColor | None = None
    top_color: str | None = None
    visibility: VisibilityLevel | None = None
    confidence: float | None = None  # 마지막 관측 시점 person 탐지 신뢰도(0~1) — 추정치임을 드러내기 위한 보조 정보
    situation_note: str | None = None  # PROLONGED_PRESENCE 전환 시 ZERO 추가 확인 결과로 채워지는 짧은 상황 설명 (app/rules/situation_probe.py)
    priority_score: float | None = None  # 확인 우선순위 점수(0~100) — app/rules/triage.py, 요청 시점에 계산해 채움(저장값 아님)


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
    """PPE 미착용이 새로 감지된 순간 1건. 이미 미착용 상태가 계속되는 동안은 매 프레임
    남기지 않고, "착용 → 미착용"으로 바뀐 순간에만 기록한다(worker_log와 같은 원칙).

    추적 ID 연속성을 신뢰하지 않는다는 전제로 설계했다 — 같은 사람이 사라졌다 다시 나타나
    새 ID를 받아도 그냥 새 위반 건으로 다시 기록될 뿐이며, 그게 의도된 동작이다. 관리자가
    frame_path의 사진을 보고 "혹시 아까 그 사람인가?"를 직접 판단하면 된다."""

    track_id: str
    violation: str  # "helmet" | "vest" — 어떤 장비가 미착용인지
    zone: str | None = None
    at: str  # ISO8601
    frame_path: str | None = None
    bbox_xyxy: tuple[float, float, float, float] | None = None
    confidence: float | None = None


class ClearanceZoneLogEntry(BaseModel):
    """관리구역 상태 변화 기록 1건 (WorkerEventLogEntry와 같은 패턴).
    evaluate_clearance_zone()이 계산한 새 상태가 직전과 다를 때만 한 줄 남긴다."""

    zone_id: str
    state: "ClearanceZoneState"
    at: str  # ISO8601
    situation_note: str | None = None  # ABNORMAL 전환 시 ZERO 추가 확인 결과(app/rules/situation_probe.py)


class IncidentTimelineEntry(BaseModel):
    """사고 리플레이 타임라인 한 줄 — 화재경보/작업자 상태변화/관리구역 상태변화/PPE
    미착용을 한 종류(source)로 통합해 시간순으로 병합한 것. app/api/incidents.py에서 조립한다."""

    at: str  # ISO8601
    source: str  # "fire_alert" | "worker" | "clearance_zone" | "ppe_violation"
    text: str  # 대시보드에 그대로 표시할 한 줄 설명
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
