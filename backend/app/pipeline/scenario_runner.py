"""데모 시나리오 재생 오케스트레이터.

`backend/scripts/precompute_demo.py`가 미리 만들어 둔 `backend/data/demo/scenario.json`을
프레임 순서대로(`demo_interval_sec` 간격으로) 재생하면서, 매 프레임마다 실제 추적
(`app.tracking.byte_track`) · 구역 판정(`app.rules.zone`) · PPE 착용 판정
(`app.rules.ppe_compliance`) · 화재경보 판정(`app.rules.alarm_trigger`) · 상태 엔진
(`app.rules.state_engine`)을 그대로 돌린다 — 재생되는 건 "미리 계산해 둔 모델 추론
결과"뿐이고, 그 위의 규칙 엔진은 매 프레임 실제로 새로 계산된다(스크립트로 짜여진
연출이 아니다).

상태 스냅샷은 프로세스 내 메모리에 유지하며 REST API(`app/api/*`)와 웹소켓
(`app/ws/live.py`)이 공유해서 읽는다. 데모 목적상 카메라 1대("demo-camera")만 가정한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2

from app.inference.detector import Detection
from app.inference.fire_detector import FireDetection
from app.inference.situation_probe import PROLONGED_PRESENCE_PROMPTS, probe_situation
from app.models.schemas import FireAlert, ObjectClass, WorkerEvent, WorkerStatus, ZoneDef, ZoneMapConfig
from app.rules import alarm_trigger, fire_alert_log, ppe_violation_log, state_engine, worker_log
from app.rules import zone as zone_rules
from app.rules.ppe_compliance import ComplianceState, evaluate_ppe_compliance
from app.tracking.byte_track import ByteTracker

logger = logging.getLogger(__name__)

DEMO_CAMERA_ID = "demo-camera"
DEMO_IMAGE_WIDTH = 1920
DEMO_IMAGE_HEIGHT = 1080
SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "demo" / "scenario.json"
FRAMES_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "frames"

# 데모는 짧은 재생 시간 안에 화재경보 후 상태 전환(장기체류경고)까지 보여줘야 하므로,
# 실제 운영 기본값(state_engine.PROLONGED_PRESENCE_MINUTES, 5분) 대신 훨씬 짧은
# 임계값을 쓴다. 운영 기본값 자체는 바뀌지 않는다 — 호출부(여기)에서만 재량으로 넘긴다.
DEMO_PROLONGED_PRESENCE_SECONDS = 8

FIRE_WINDOW_SIZE = 5
FIRE_MIN_HIT_RATIO = 0.6
# development_log.md 참고: optimal_confidence(0.44)는 배경 오탐이 많아 데모에서는
# 더 보수적인 값을 쓴다. precompute 단계에서 이미 0.65 이상만 저장했으므로, 여기서는
# 그 결과를 그대로 신뢰한다.
FIRE_CONFIDENCE_THRESHOLD = 0.6


def _register_demo_zone_map() -> None:
    """데모 카메라 화면을 좌/우 절반으로 나눠 A구역/B구역으로 등록.
    화면 5(구역 설정)에서 그대로 조회·수정할 수 있도록 실제 zone.py 저장 경로를 쓴다."""
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
    frame_image_url: str | None = None
    frame_width: int = DEMO_IMAGE_WIDTH
    frame_height: int = DEMO_IMAGE_HEIGHT
    fire_alert: FireAlert | None = None
    workers: dict[str, WorkerStatus] = field(default_factory=dict)
    event_feed: list[dict] = field(default_factory=list)
    ppe_violations_today: int = 0
    zone_person_counts: dict[str, int] = field(default_factory=dict)
    # track_id -> 직전 프레임의 (helmet, vest) 착용 상태. "착용→미착용"으로 막 바뀐 순간만
    # 로그로 남기기 위한 비교용(매 프레임 기록 방지). 추적 ID가 끊기면 그냥 새 항목으로
    # 다시 시작된다 — ID 연속성을 신뢰하지 않는다는 설계 원칙과 일치.
    ppe_compliance_prev: dict[str, tuple[ComplianceState, ComplianceState]] = field(default_factory=dict)
    # 화면에 bbox 오버레이를 그리기 위한 현재 프레임의 원본 탐지 결과(추적 ID 부여 전).
    current_detections: list[dict] = field(default_factory=list)


STATE = DemoState()
_listeners: list[Callable[[dict], Awaitable[None]]] = []


def add_listener(fn: Callable[[dict], Awaitable[None]]) -> None:
    _listeners.append(fn)


def remove_listener(fn: Callable[[dict], Awaitable[None]]) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def snapshot_dict() -> dict:
    return {
        "running": STATE.running,
        "frame_idx": STATE.frame_idx,
        "frame_image_url": STATE.frame_image_url,
        "frame_width": STATE.frame_width,
        "frame_height": STATE.frame_height,
        "fire_alert": STATE.fire_alert.model_dump() if STATE.fire_alert else None,
        "workers": [w.model_dump() for w in STATE.workers.values()],
        "event_feed": STATE.event_feed[-30:],
        "ppe_violations_today": STATE.ppe_violations_today,
        "zone_person_counts": STATE.zone_person_counts,
        "current_detections": STATE.current_detections,
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


async def _probe_prolonged_presence(camera_id: str, track_id: str, frame_path_rel: str | None) -> None:
    """PROLONGED_PRESENCE 전환 시점에만 ZERO로 2차 확인을 비동기로 돌린다.

    프레임 재생 루프를 막지 않도록 별도 태스크로 띄운다(await asyncio.to_thread) — ZERO 호출은
    네트워크 왕복이 있는 동기 함수라, 루프 안에서 직접 기다리면 그동안 데모 재생이 멈춘다.
    결과가 오면 현재 상태(STATE, 실시간 표시용)와 로그(worker_log, 사고 리플레이용) 둘 다 채운다.
    """
    if frame_path_rel is None:
        return
    frame = cv2.imread(str(FRAMES_DIR / frame_path_rel))
    if frame is None:
        return
    try:
        note = await asyncio.to_thread(probe_situation, frame, PROLONGED_PRESENCE_PROMPTS)
    except Exception:
        logger.warning("PROLONGED_PRESENCE 2차 확인 실패", exc_info=True)
        return
    if note is None:
        return
    worker = STATE.workers.get(track_id)
    if worker is not None and worker.event == WorkerEvent.PROLONGED_PRESENCE:
        worker.situation_note = note
    worker_log.update_last_situation_note(camera_id, track_id, note)
    _add_event(f"{track_id} 2차 확인: {note}", datetime.now(UTC))
    await _broadcast()


def reset() -> None:
    global STATE
    STATE = DemoState()


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
    interval = data.get("demo_interval_sec", 1.0) / max(speed, 0.01)
    frames = data["frames"]

    tracker = ByteTracker()
    fire_window: list[list[FireDetection]] = []
    fire_triggered_at: datetime | None = None
    sim_start = datetime.now(UTC)

    STATE.running = True
    _add_event("시나리오 재생 시작", sim_start)
    await _broadcast()

    for frame in frames:
        STATE.frame_idx = frame["idx"]
        STATE.frame_image_url = f"/demo-frames/{frame['frame_path']}"
        now = sim_start + timedelta(seconds=frame["t"])

        all_dets = _parse_detections(frame["person_detections"])
        person_dets = [d for d in all_dets if d.object_class == ObjectClass.PERSON]
        helmet_boxes = [d.bbox_xyxy for d in all_dets if d.object_class == ObjectClass.HELMET]
        vest_boxes = [d.bbox_xyxy for d in all_dets if d.object_class == ObjectClass.VEST]
        STATE.current_detections = [
            {"object_class": d.object_class.value, "confidence": d.confidence, "bbox_xyxy": list(d.bbox_xyxy)}
            for d in all_dets
        ]

        tracked = tracker.update(person_dets)

        # --- 화재/연기 경보 판정 (매 프레임 실제로 계산, 한 번 트리거되면 이 시나리오 동안 유지) ---
        fire_dets = _parse_fire_detections(frame["fire_detections"])
        fire_window.append(fire_dets)
        fire_window = fire_window[-FIRE_WINDOW_SIZE:]

        if fire_triggered_at is None:
            alert = alarm_trigger.evaluate(
                DEMO_CAMERA_ID,
                fire_window,
                confidence_threshold=FIRE_CONFIDENCE_THRESHOLD,
                min_hit_ratio=FIRE_MIN_HIT_RATIO,
            )
            if alert is not None:
                fire_triggered_at = now
                STATE.fire_alert = alert
                fire_alert_log.append_fire_alert(alert)
                conf_str = f"{alert.confidence:.2f}" if alert.confidence is not None else "N/A"
                _add_event(f"🔥 화재경보 발생 (자동탐지, 신뢰도 {conf_str})", now)

        # --- 사람별 추적 → 구역 판정 → PPE 판정 → 상태 엔진 ---
        zone_counts: dict[str, int] = {}
        seen_ids: set[str] = set()
        for t in tracked:
            seen_ids.add(t.track_id)
            cx, cy = (t.detection.bbox_xyxy[0] + t.detection.bbox_xyxy[2]) / 2, (t.detection.bbox_xyxy[1] + t.detection.bbox_xyxy[3]) / 2
            zone_id = zone_rules.which_zone(DEMO_CAMERA_ID, (cx, cy)) or "미분류"
            zone_counts[zone_id] = zone_counts.get(zone_id, 0) + 1

            compliance = evaluate_ppe_compliance(t.detection.bbox_xyxy, helmet_boxes=helmet_boxes, vest_boxes=vest_boxes)
            if compliance.helmet == ComplianceState.NOT_WORN or compliance.vest == ComplianceState.NOT_WORN:
                STATE.ppe_violations_today += 1

            prev_helmet, prev_vest = STATE.ppe_compliance_prev.get(t.track_id, (ComplianceState.UNKNOWN, ComplianceState.UNKNOWN))
            for violation_name, current_state, prev_state in (
                ("helmet", compliance.helmet, prev_helmet),
                ("vest", compliance.vest, prev_vest),
            ):
                if current_state == ComplianceState.NOT_WORN:
                    ppe_violation_log.record_if_newly_violated(
                        DEMO_CAMERA_ID,
                        t.track_id,
                        violation=violation_name,
                        was_violated_before=prev_state == ComplianceState.NOT_WORN,
                        zone=zone_id,
                        now_iso=now.isoformat(),
                        frame_path=STATE.frame_image_url,
                        bbox_xyxy=t.detection.bbox_xyxy,
                        confidence=t.detection.confidence,
                    )
                    if prev_state != ComplianceState.NOT_WORN:
                        _add_event(f"{t.track_id} {zone_id}에서 {violation_name} 미착용 감지", now)
            STATE.ppe_compliance_prev[t.track_id] = (compliance.helmet, compliance.vest)

            prev = STATE.workers.get(t.track_id)
            status = state_engine.resolve_status(
                t.track_id,
                is_currently_observed=True,
                now=now,
                fire_triggered_at=fire_triggered_at,
                last_zone=zone_id,
                last_seen_at=now.isoformat(),
                last_frame_path=STATE.frame_image_url,
                prolonged_presence_minutes=DEMO_PROLONGED_PRESENCE_SECONDS / 60,
            )
            status.confidence = t.detection.confidence
            worker_log.record_if_changed(DEMO_CAMERA_ID, prev, status, now.isoformat(), bbox_xyxy=t.detection.bbox_xyxy)
            if prev is None:
                _add_event(f"{t.track_id} {zone_id}에서 관측 시작", now)
            elif prev.event != status.event:
                _add_event(f"{t.track_id} 상태 변화: {prev.event.value} → {status.event.value}", now)
                if status.event == WorkerEvent.PROLONGED_PRESENCE:
                    asyncio.create_task(_probe_prolonged_presence(DEMO_CAMERA_ID, t.track_id, frame.get("frame_path")))
            STATE.workers[t.track_id] = status

        # 이번 프레임에 안 잡힌(추적 소실) 기존 작업자는 tracking_lost로 갱신
        for track_id, prev in list(STATE.workers.items()):
            if track_id in seen_ids or prev.event == WorkerEvent.TRACKING_LOST:
                continue
            status = state_engine.resolve_status(
                track_id,
                is_currently_observed=False,
                now=now,
                fire_triggered_at=fire_triggered_at,
                last_zone=prev.last_zone,
                last_seen_at=prev.last_seen_at,
                last_frame_path=prev.last_frame_path,
                prolonged_presence_minutes=DEMO_PROLONGED_PRESENCE_SECONDS / 60,
            )
            worker_log.record_if_changed(DEMO_CAMERA_ID, prev, status, now.isoformat())
            _add_event(f"{track_id} 관측 끊김 (마지막: {prev.last_zone})", now)
            STATE.workers[track_id] = status

        STATE.zone_person_counts = zone_counts
        await _broadcast()
        await asyncio.sleep(interval)

    STATE.running = False
    await _broadcast()
