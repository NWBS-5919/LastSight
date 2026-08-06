"""데모 시나리오 재생 오케스트레이터.

`backend/scripts/precompute_demo.py`가 미리 만들어 둔 `backend/data/demo/scenario.json`을
프레임 순서대로(`demo_interval_sec` 간격으로) 재생하면서, 매 프레임마다 실제 구역 판정
(`app.rules.zone`) · 화재경보 판정(`app.rules.alarm_trigger`)을 그대로 돌린다 — 재생되는
건 "미리 계산해 둔 모델 추론 결과"뿐이고, 그 위의 규칙 엔진은 매 프레임 실제로 새로
계산된다(스크립트로 짜여진 연출이 아니다).

2026-08-02 재설계(평상시/비상시 분기): 평상시엔 사람이 화면을 들락날락할 때마다 추적
ID가 계속 새로 매겨지는 게 의미가 없어(development_log.md 43번) 추적(ByteTracker) 자체를
쓰지 않는다 — person 박스마다 구역과 PPE 착용만 그때그때 판정하고, 위반은 위치+시간
기반으로 중복 없이 기록한다(app.rules.ppe_violation_log). 화재경보가 뜨는 순간부터는
반대로 "얼마나 오래 관측되고 있는지"를 재야 하므로 그때부터 추적을 시작하고, 대신
PPE 판정은 건너뛴다(우선순위가 아니므로). 장기체류(PROLONGED_PRESENCE) 전환이 하나라도
생기면 그 순간 전체 구역을 다시 집계해 2차 확인(ZERO)과 함께 로그로 남긴다
(app.rules.zone_situation_log).

상태 스냅샷은 프로세스 내 메모리에 유지하며 REST API(`app/api/*`)와 웹소켓
(`app/ws/live.py`)이 공유해서 읽는다. 데모 목적상 카메라 1대("demo-camera")만 가정한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2

from app.inference.detector import Detection
from app.inference.fire_detector import FireDetection
from app.inference.situation_probe import STAY_CATEGORY, probe_zone_situation
from app.models.schemas import (
    FireAlert,
    ObjectClass,
    PersonComplianceBox,
    PpeViolationLogEntry,
    WorkerStatus,
    ZoneDef,
    ZoneMapConfig,
    ZoneSituationBox,
    ZoneSituationEntry,
    ZoneSituationLogEntry,
)
from app.rules import alarm_trigger, fire_alert_log, ppe_settings, ppe_violation_log, zone_situation_log
from app.rules import zone as zone_rules
from app.rules.ppe_compliance import ComplianceState, evaluate_ppe_compliance, reset_display_streams, stabilize_display

logger = logging.getLogger(__name__)

DEMO_CAMERA_ID = "demo-camera"
DEMO_IMAGE_WIDTH = 1920
DEMO_IMAGE_HEIGHT = 1080
SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "demo" / "scenario.json"
FRAMES_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "frames"

# 2026-08-03 재설계: 추적(개인별 장기체류 판정) 기반 2차 확인 트리거를 없애고, 화재 발생
# 후 이 간격(초)마다 무조건 그 순간 프레임을 ZERO로 확인해 카드를 쌓는다 — "누가 얼마나
# 오래 있었는지"가 아니라 "지금 이 순간 무엇이 보이는지"를 매초 기록하는 방식으로
# 바꿨다(추적 오재부착 문제를 근본적으로 없애기 위함, development_log.md 참고).
SITUATION_PROBE_INTERVAL_SECONDS = 1

# 화재 판정은 5초 주기 샘플링·2회 연속 감지를 가정한다(app.rules.alarm_trigger). 데모는
# 그보다 훨씬 촘촘한 간격으로 프레임을 재생하므로, 실제 5초 간격 샘플링을 흉내내기보다
# "최근 이 정도 개수는 계속 들고 있는다"는 정도로만 윈도우를 유지한다.
#
# 2026-08-03: 화재 이후 구간을 추적 안정성을 위해 0.25초 간격(기존 1초 대비 4배)으로
# 재생성하면서, 이 값도 2→8로 같이 올렸다 — 그대로 뒀으면 "연속 2회 확정"이 실질적으로
# 0.5초 확정이 돼버려 단발 오탐 방지 효과가 거의 사라진다. 8회×0.25초=2초로, 원래
# 데모가 갖고 있던 "연속 2회×1초=2초" 확정 시간과 동일하게 맞췄다.
FIRE_CONSECUTIVE_REQUIRED = 8
# 2026-08-02 정정: 이전엔 "precompute 단계에서 이미 0.65 이상만 저장한다"는 전제로 여기
# 게이트를 0.6으로 뒀는데, 이건 커스텀 fire-smoke-v4 모델(신뢰도가 높게 나옴) 기준이었다.
# 지금은 v4가 일반화 문제로 비활성화돼(fire_detector.py 참고) ZERO 폴백을 쓰는데, ZERO가
# 실제 화염 영상(LastSight_Demo.mp4)에서 보고하는 신뢰도는 0.34~0.58에 그쳐(실측) 0.6을
# 절대 못 넘어 경보가 영원히 안 울렸다. 같은 영상의 화재 이전 구간(0~59초)에서는 fire가
# 단 한 번도 오탐되지 않은 것도 확인했으므로, ZERO 폴백 범위에 맞춰 낮췄다.
FIRE_CONFIDENCE_THRESHOLD = 0.35

BBox = tuple[float, float, float, float]


def _register_demo_zone_map() -> None:
    """데모 카메라 화면을 좌/우 절반으로 나눠 A구역/B구역으로 등록(최초 1회만).
    화면 5(구역 설정)에서 그대로 조회·수정할 수 있도록 실제 zone.py 저장 경로를 쓴다.

    2026-08-03: 이 함수가 run_scenario()에서 매번(시나리오 "시작" 버튼을 누를 때마다)
    무조건 호출되면서, 관리자가 구역 편집 화면에서 새로 그려 저장한 구역이 시나리오를
    다시 시작하는 순간 A/B 절반 분할로 덮어써지는 버그가 있었다(실측 — 사용자가 새 구역을
    만들어도 실시간 인원수·PPE/구조 카드에는 여전히 A/B구역만 나타남). 구역 설정 파일이
    이미 있으면 절대 건드리지 않고, 파일 자체가 없는 최초 부팅 시에만 기본값을 만든다."""
    if zone_rules.zone_map_path(DEMO_CAMERA_ID).exists():
        return
    config = ZoneMapConfig(
        camera_id=DEMO_CAMERA_ID,
        image_width=DEMO_IMAGE_WIDTH,
        image_height=DEMO_IMAGE_HEIGHT,
        zones=[
            ZoneDef(zone_id="A구역", polygon=[(0, 0), (DEMO_IMAGE_WIDTH / 2, 0), (DEMO_IMAGE_WIDTH / 2, DEMO_IMAGE_HEIGHT), (0, DEMO_IMAGE_HEIGHT)]),
            ZoneDef(zone_id="B구역", polygon=[(DEMO_IMAGE_WIDTH / 2, 0), (DEMO_IMAGE_WIDTH, 0), (DEMO_IMAGE_WIDTH, DEMO_IMAGE_HEIGHT), (DEMO_IMAGE_WIDTH / 2, DEMO_IMAGE_HEIGHT)]),
        ],
    )
    zone_rules.save_zone_map(config)


@dataclass
class DemoState:
    running: bool = False
    frame_idx: int = -1
    # 이 프레임이 원본 영상 기준 몇 초 지점인지(frame["t"]) — 프론트엔드가 <video> 재생
    # 위치를 이 값에 맞춰 보정하는 데 쓴다(2026-08-03, 아래 run_scenario의 target_elapsed
    # 계산과 같은 이유: 화재 이후 구간이 촘촘해지며 프레임 간격이 더 이상 균일하지 않다).
    frame_t: float | None = None
    frame_image_url: str | None = None
    frame_width: int = DEMO_IMAGE_WIDTH
    frame_height: int = DEMO_IMAGE_HEIGHT
    fire_alert: FireAlert | None = None
    # 2026-08-03: 추적 기반 개인별 작업자 목록은 더 이상 채우지 않는다(항상 빈 dict) —
    # app/api/workers.py·app/api/briefing.py가 이 필드를 계속 참조하므로 타입 호환을 위해
    # 필드 자체는 남겨둔다. 대시보드는 대신 situation_checks(아래)를 쓴다.
    workers: dict[str, WorkerStatus] = field(default_factory=dict)
    event_feed: list[dict] = field(default_factory=list)
    zone_person_counts: dict[str, int] = field(default_factory=dict)
    # 화면에 bbox 오버레이를 그리기 위한 현재 프레임의 원본 탐지 결과(추적 ID 부여 전).
    current_detections: list[dict] = field(default_factory=list)
    # 평상시 화면에 "헬멧 착용"/"헬멧 미착용" 실시간 라벨을 그리기 위한, 사람별 착용 판정
    # 스냅샷(이번 프레임에 한정, 추적 없음). 비상시엔 PPE 판정 자체를 안 하므로 항상 빈 리스트.
    current_person_compliance: list[PersonComplianceBox] = field(default_factory=list)
    # 화재 발생 후 1초마다 쌓이는 2차 확인(ZERO) 카드 — 평상시 PPE 위반 로그와 같은 성격의
    # "그 순간의 사실 기록" append-only 목록. 프론트가 이걸로 하단 카드 그리드를 그린다.
    situation_checks: list[ZoneSituationLogEntry] = field(default_factory=list)
    # 시나리오 재생이 시작된 시각(ISO8601) — 평상시 타임라인이 "영상 시작"을 t=0 기준점으로
    # 잡는 데 쓴다(비상시 타임라인이 fire_alert.triggered_at을 기준으로 삼는 것과 동일한 패턴).
    scenario_started_at: str | None = None
    # 평상시 PPE 미착용이 새로 감지될 때마다 쌓이는 라이브 목록 — situation_checks와 같은
    # 패턴. 카드를 눌러 검토·수정하면 이 목록의 해당 항목도 갱신된다(app/api/ppe.py 참고).
    ppe_violation_events: list[PpeViolationLogEntry] = field(default_factory=list)


STATE = DemoState()
_listeners: list[Callable[[dict], Awaitable[None]]] = []

# 2026-08-03: asyncio.create_task()의 반환값을 아무 데도 저장하지 않으면, 이벤트 루프는
# 태스크를 약한 참조로만 들고 있어서 다른 참조가 없으면 완료 전에 가비지 컬렉션될 수 있다
# (실측 — 2차 확인 태스크가 매번 조용히 사라져 zone_situation_log가 계속 비어있었다).
# 참조를 유지했다가 끝나면 스스로 정리하는 최소 구현.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro: Awaitable[None]) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def add_listener(fn: Callable[[dict], Awaitable[None]]) -> None:
    _listeners.append(fn)


def remove_listener(fn: Callable[[dict], Awaitable[None]]) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def snapshot_dict() -> dict:
    return {
        "running": STATE.running,
        "frame_idx": STATE.frame_idx,
        "frame_t": STATE.frame_t,
        "frame_image_url": STATE.frame_image_url,
        "frame_width": STATE.frame_width,
        "frame_height": STATE.frame_height,
        "fire_alert": STATE.fire_alert.model_dump() if STATE.fire_alert else None,
        "workers": [w.model_dump() for w in STATE.workers.values()],
        "event_feed": STATE.event_feed[-30:],
        # 2026-08-06: 예전엔 위반이 새로 생길 때마다 STATE.ppe_violations_today를 따로
        # +1 했는데, merge_ppe_violations()가 ppe_violation_events는 줄이면서 이 카운터는
        # 안 건드려서 병합 후 숫자가 실제 타임라인/카드 개수보다 커지는 어긋남이 있었다
        # (사용자 지적). 별도 카운터 없이 항상 ppe_violation_events 길이에서 그대로
        # 계산해서, 대시보드 숫자가 타임라인에 보이는 것과 항상 정확히 같도록 했다.
        "ppe_violations_today": len(STATE.ppe_violation_events),
        "zone_person_counts": STATE.zone_person_counts,
        "current_detections": STATE.current_detections,
        "current_person_compliance": [p.model_dump() for p in STATE.current_person_compliance],
        "situation_checks": [e.model_dump() for e in STATE.situation_checks],
        "scenario_started_at": STATE.scenario_started_at,
        "ppe_violation_events": [e.model_dump() for e in STATE.ppe_violation_events],
    }


async def _broadcast() -> None:
    snap = snapshot_dict()
    for fn in list(_listeners):
        try:
            await fn(snap)
        except Exception:
            pass


def _add_event(text: str, now: datetime) -> None:
    STATE.event_feed.append({"at": now.isoformat(), "text": text})


def _format_zone_situation_text(zones: list[ZoneSituationEntry]) -> str:
    """구조카드/이벤트 피드용 한 줄 요약. 예: "A구역 총 4명(체류중 1, 쓰러진 사람 3) / B구역 총 2명(...)"."""
    parts = []
    for z in zones:
        breakdown_str = ", ".join(f"{k} {v}명" for k, v in z.breakdown.items() if v > 0)
        parts.append(f"{z.zone_id} 총 {z.total}명({breakdown_str})")
    return " / ".join(parts)


async def _probe_frame_situation_and_log(
    camera_id: str,
    now: datetime,
    fire_triggered_at: datetime | None,
    frame_path_rel: str | None,
    frame_image_url: str | None,
    person_dets: list[Detection],
) -> None:
    """화재 발생 후 1초마다(SITUATION_PROBE_INTERVAL_SECONDS) 그 순간 프레임 전체를
    ZERO로 2차 확인해 카드 하나를 쌓는다.

    2026-08-03 재설계: 예전엔 "누군가 장기체류경고로 전환되는 순간"에만, 추적 중인
    작업자 목록(workers_by_zone)을 기준으로 실행했다. 이제 추적 자체를 안 쓰므로, 이번
    프레임에 실제로 감지된 person_dets에 임시 번호(P0, P1, ...)만 붙여 같은 방식
    (app.inference.situation_probe.probe_zone_situation, 중심점 거리 매칭)으로 위치
    매칭한다 — 이 번호는 이번 호출 안에서만 쓰이고 다음 호출로 이어지지 않는다(지속
    추적이 아니므로 오재부착 문제 자체가 생기지 않는다).

    프레임 재생 루프를 막지 않도록 별도 태스크로 띄운다(await asyncio.to_thread) — ZERO 호출은
    네트워크 왕복이 있는 동기 함수라, 루프 안에서 직접 기다리면 그동안 데모 재생이 멈춘다.
    """
    if frame_path_rel is None or not person_dets:
        return
    frame = cv2.imread(str(FRAMES_DIR.parent / frame_path_rel))
    if frame is None:
        return

    workers_by_zone: dict[str, list[tuple[str, BBox]]] = {}
    for i, det in enumerate(person_dets):
        cx, cy = (det.bbox_xyxy[0] + det.bbox_xyxy[2]) / 2, (det.bbox_xyxy[1] + det.bbox_xyxy[3]) / 2
        zone_id = zone_rules.which_zone(camera_id, (cx, cy)) or "미분류"
        workers_by_zone.setdefault(zone_id, []).append((f"P{i}", det.bbox_xyxy))

    try:
        breakdown_by_zone, matched_category = await asyncio.to_thread(probe_zone_situation, frame, workers_by_zone)
    except Exception:
        logger.warning("상황 2차 확인 실패", exc_info=True)
        return

    zones = [
        ZoneSituationEntry(
            zone_id=zone_id,
            total=sum(breakdown.values()),
            breakdown=breakdown,
            boxes=[
                ZoneSituationBox(category=matched_category.get(pid, STAY_CATEGORY), bbox_xyxy=bbox)
                for pid, bbox in workers_by_zone.get(zone_id, [])
            ],
        )
        for zone_id, breakdown in breakdown_by_zone.items()
    ]
    elapsed_seconds = (now - fire_triggered_at).total_seconds() if fire_triggered_at is not None else None
    entry = ZoneSituationLogEntry(camera_id=camera_id, at=now.isoformat(), zones=zones, frame_path=frame_image_url)
    zone_situation_log.append_zone_situation(entry)
    STATE.situation_checks.append(entry)

    label = f"화재 발생 후 {round(elapsed_seconds)}초" if elapsed_seconds is not None else "2차 확인"
    _add_event(f"{label}: {_format_zone_situation_text(zones)}", now)
    await _broadcast()


def reset() -> None:
    # STATE 객체 자체를 새로 만들지 않고 기존 객체의 필드를 갈아끼운다 — `global STATE;
    # STATE = DemoState()`로 이름을 재할당하면, `from app.pipeline.scenario_runner import
    # STATE`처럼 이름으로 들여온 다른 모듈은 그 시점의 옛 객체를 계속 붙든 채 절대 갱신되지
    # 않는다(실측 — app/api/workers.py가 항상 빈 STATE만 보고 더미 데이터로 계속 폴백했다).
    # 객체를 계속 재사용하면 이런 import 방식 차이와 무관하게 항상 최신 상태를 본다.
    STATE.__dict__.update(DemoState().__dict__)
    # PPE 판정/위반로그가 쓰는 스트림 메모리(모듈 전역, reset()과 별개로 계속 누적)도 같이
    # 비운다 — 안 그러면 재생을 반복할 때마다 지난 재생의 스트림이 새 재생에 이어붙어
    # 미착용 확정 타이밍이 재생마다 달라진다(실측).
    reset_display_streams(DEMO_CAMERA_ID)
    ppe_violation_log.reset_streams(DEMO_CAMERA_ID)


def _parse_detections(rows: list[dict]) -> list[Detection]:
    return [
        Detection(object_class=ObjectClass(d["object_class"]), confidence=d["confidence"], bbox_xyxy=tuple(d["bbox_xyxy"]))
        for d in rows
    ]


def _parse_fire_detections(rows: list[dict]) -> list[FireDetection]:
    return [
        FireDetection(object_class=ObjectClass(d["object_class"]), confidence=d["confidence"], bbox_xyxy=tuple(d["bbox_xyxy"]))
        for d in rows
    ]


async def run_scenario(speed: float = 1.0) -> None:
    """scenario.json을 재생. speed=1.0이면 원래 demo_interval_sec 그대로, 2.0이면 2배속."""
    reset()
    _register_demo_zone_map()
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    frames = data["frames"]

    fire_window: list[list[FireDetection]] = []
    fire_triggered_at: datetime | None = None
    last_situation_probe_at: datetime | None = None
    sim_start = datetime.now(UTC)
    STATE.scenario_started_at = sim_start.isoformat()
    # 2026-08-03: 프론트엔드가 원본 영상을 실제 <video>로 재생하기 시작하면서(48-50번과
    # 별개로, 지금까지의 "정지 이미지 슬라이드쇼" 대신) 박스 갱신이 영상 재생 속도와 눈에
    # 띄게 어긋나는 문제가 생겼다 — 원인은 매 반복이 `await asyncio.sleep(interval)`로
    # "고정 간격만큼만" 쉬어서, 그 앞의 규칙 엔진 계산·웹소켓 브로드캐스트에 걸린 시간이
    # 전혀 보정되지 않고 매 프레임 그대로 누적됐기 때문이다(87번 반복하면 수 초까지 밀릴 수
    # 있음). 시스템 시계 변경에 영향받지 않는 단조 시계(`time.monotonic`) 기준으로 "각
    # 프레임이 나가야 할 목표 시각"을 미리 계산해두고, 그 시각까지 남은 만큼만 자도록 바꿔
    # 계산 시간이 얼마가 걸리든 실제 재생 속도(interval)를 그대로 따라가게 했다.
    loop_start_monotonic = time.monotonic()

    STATE.running = True
    _add_event("시나리오 재생 시작", sim_start)
    await _broadcast()

    for sample_idx, frame in enumerate(frames):
        STATE.frame_idx = frame["idx"]
        STATE.frame_t = frame["t"]
        STATE.frame_image_url = f"/demo-frames/{frame['frame_path']}"
        now = sim_start + timedelta(seconds=frame["t"])

        all_dets = _parse_detections(frame["person_detections"])
        person_dets = [d for d in all_dets if d.object_class == ObjectClass.PERSON]
        helmet_boxes = [d.bbox_xyxy for d in all_dets if d.object_class == ObjectClass.HELMET]
        vest_boxes = [d.bbox_xyxy for d in all_dets if d.object_class == ObjectClass.VEST]
        head_boxes = [tuple(b) for b in frame.get("head_boxes", [])]
        upper_body_boxes = [tuple(b) for b in frame.get("upper_body_boxes", [])]
        STATE.current_detections = [
            {"object_class": d.object_class.value, "confidence": d.confidence, "bbox_xyxy": list(d.bbox_xyxy)}
            for d in all_dets
        ]

        # --- 화재/연기 경보 판정 (매 프레임 실제로 계산, 한 번 트리거되면 이 시나리오 동안 유지) ---
        fire_dets = _parse_fire_detections(frame["fire_detections"])
        fire_window.append(fire_dets)
        fire_window = fire_window[-FIRE_CONSECUTIVE_REQUIRED:]

        if fire_triggered_at is None:
            alert = alarm_trigger.evaluate(
                DEMO_CAMERA_ID,
                fire_window,
                confidence_threshold=FIRE_CONFIDENCE_THRESHOLD,
                consecutive_required=FIRE_CONSECUTIVE_REQUIRED,
            )
            if alert is not None:
                fire_triggered_at = now
                STATE.fire_alert = alert
                fire_alert_log.append_fire_alert(alert)
                conf_str = f"{alert.confidence:.2f}" if alert.confidence is not None else "N/A"
                _add_event(f"🔥 화재경보 발생 (자동탐지, 신뢰도 {conf_str})", now)

        zone_counts: dict[str, int] = {}

        if fire_triggered_at is None:
            # --- 평상시: 추적 없이 person 박스마다 구역 판정 + PPE 착용 판정만 한다.
            # 추적 ID가 없으므로 위반 중복 여부는 위치+시간 기반으로 판단한다
            # (app.rules.ppe_violation_log의 스페이셜 dedup).
            settings = ppe_settings.load_ppe_settings(DEMO_CAMERA_ID)
            person_compliance: list[PersonComplianceBox] = []
            for det in person_dets:
                cx, cy = (det.bbox_xyxy[0] + det.bbox_xyxy[2]) / 2, (det.bbox_xyxy[1] + det.bbox_xyxy[3]) / 2
                zone_id = zone_rules.which_zone(DEMO_CAMERA_ID, (cx, cy)) or "미분류"
                zone_counts[zone_id] = zone_counts.get(zone_id, 0) + 1

                compliance = evaluate_ppe_compliance(
                    det.bbox_xyxy,
                    head_boxes=head_boxes,
                    helmet_boxes=helmet_boxes,
                    vest_boxes=vest_boxes,
                    upper_body_boxes=upper_body_boxes,
                    detect_helmet=settings.detect_helmet,
                    detect_vest=settings.detect_vest,
                )
                # 순간 판정을 그대로 쓰지 않고, 같은 위치에서 연속 2회 같은 방향으로 나와야
                # 화면 표시가 바뀐다 — 미착용 확정도, 다시 착용으로 돌아오는 것도 동일하게
                # (대칭 히스테리시스, app.rules.ppe_compliance.stabilize_display).
                display_helmet = stabilize_display(
                    DEMO_CAMERA_ID, zone=zone_id, ppe_type="helmet", raw_state=compliance.helmet, bbox_xyxy=det.bbox_xyxy, now=now
                )
                display_vest = stabilize_display(
                    DEMO_CAMERA_ID, zone=zone_id, ppe_type="vest", raw_state=compliance.vest, bbox_xyxy=det.bbox_xyxy, now=now
                )
                violations = [
                    name for name, state in (("helmet", display_helmet), ("vest", display_vest)) if state == ComplianceState.NOT_WORN
                ]
                logged = ppe_violation_log.record_if_new_violation(
                    DEMO_CAMERA_ID,
                    zone=zone_id,
                    violations=violations,
                    now_iso=now.isoformat(),
                    frame_path=STATE.frame_image_url,
                    bbox_xyxy=det.bbox_xyxy,
                    confidence=det.confidence,
                    helmet_state=display_helmet.value,
                    vest_state=display_vest.value,
                )
                person_compliance.append(
                    PersonComplianceBox(
                        bbox_xyxy=det.bbox_xyxy,
                        zone=zone_id,
                        helmet=display_helmet.value,
                        vest=display_vest.value,
                        confidence=det.confidence,
                    )
                )
                if logged is not None:
                    STATE.ppe_violation_events.append(logged)
                    _add_event(f"{zone_id}에서 {ppe_violation_log.format_violation_text(violations)} 감지", now)
            STATE.current_person_compliance = person_compliance
            STATE.workers = {}  # 평상시엔 추적 자체를 안 하므로 워커 목록은 비워둔다
        else:
            STATE.current_person_compliance = []  # 비상시엔 PPE 판정 자체를 안 함
            STATE.workers = {}  # 개인별 추적 상태는 더 이상 안 씀(아래 설명) — 항상 비움
            # --- 비상시: 2026-08-03 재설계. 추적 기반 개인별 상태(관측중/장기체류경고 등)를
            # 걷어냈다 — track_id 없이 순수 위치만으로 "오래 놓친 사람 자리에 다른 사람이
            # 나타나면 같은 사람으로 이어붙이는" 오재부착을 근본적으로 막을 방법이 없었다
            # (실측 — 문에서 들어온 사람의 ID가 몇 초 뒤 전기패널 옆의 다른 사람에게 그대로
            # 넘어감). 대신 평상시와 같은 원칙(추적 없이, 이번 프레임에 실제로 보이는 것만
            # 다룸)으로 돌아가되, "얼마나 오래 있었는지"가 아니라 "지금 이 순간 무엇이
            # 보이는지"를 매초 스냅샷으로 남기는 방식으로 바꿨다 — 사람은 전원 초록 박스로만
            # 표시하고(개인별 상태 구분 없음), 화재 발생 후 1초마다 그 프레임을 ZERO로 2차
            # 확인해 카드를 쌓는다(누적 인원 추정이 아니라 그 순간의 사실 기록).
            for det in person_dets:
                cx, cy = (det.bbox_xyxy[0] + det.bbox_xyxy[2]) / 2, (det.bbox_xyxy[1] + det.bbox_xyxy[3]) / 2
                zone_id = zone_rules.which_zone(DEMO_CAMERA_ID, (cx, cy)) or "미분류"
                zone_counts[zone_id] = zone_counts.get(zone_id, 0) + 1

            due = (
                last_situation_probe_at is None
                or (now - last_situation_probe_at).total_seconds() >= SITUATION_PROBE_INTERVAL_SECONDS
            )
            if due:
                last_situation_probe_at = now
                _spawn_background(
                    _probe_frame_situation_and_log(DEMO_CAMERA_ID, now, fire_triggered_at, frame.get("frame_path"), STATE.frame_image_url, person_dets)
                )

        STATE.zone_person_counts = zone_counts
        await _broadcast()

        # 2026-08-03: 화재 이후 구간을 훨씬 촘촘한 간격(0.25초)으로 다시 만들면서, 프레임
        # 간격이 더 이상 일정(demo_interval_sec)하지 않게 됐다 — sample_idx*interval로
        # 목표 시각을 계산하면 뒤쪽 촘촘한 구간에서 실제 영상(및 화면의 <video> 재생
        # 속도)보다 훨씬 느리게 재생돼 다시 어긋난다. 각 프레임이 실제로 몇 초 지점인지
        # (frame["t"], precompute 단계에서 원본 영상 시간 기준으로 이미 정확히 계산해 둠)를
        # 그대로 목표 시각으로 쓴다 — 간격이 균일하든 아니든 항상 원본 영상 재생 속도를
        # 그대로 따라간다.
        target_elapsed = frame["t"] / max(speed, 0.01)
        remaining = target_elapsed - (time.monotonic() - loop_start_monotonic)
        if remaining > 0:
            await asyncio.sleep(remaining)

    STATE.running = False
    await _broadcast()
