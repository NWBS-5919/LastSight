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


class WorkerEventLogEntry(BaseModel):
    """작업자 타임라인에 표시할 상태 변화 기록 1건. resolve_status()가 이전 상태 대비
    event가 실제로 바뀔 때만 이 로그를 추가한다(매 프레임 남기지 않음)."""

    track_id: str
    event: WorkerEvent
    zone: str | None = None
    at: str  # ISO8601


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
