"""LastSight 파이프라인 전체를 한 영상으로 시연 — 평상시 PPE 감시 → 화재 감지 → 비상시
관측/2차 검증까지, scenario_runner.py와 같은 규칙 모듈을 그대로 불러써서 실제 판정 로직으로
프레임을 그린다(연출이 아니라 진짜 규칙 엔진).

흐름:
  평상시(화재 전): person/helmet/vest 감지 → 구역 판정 + PPE 착용 판정
    (app.rules.ppe_compliance, head 알고리즘 없이 "안 잡히면 미착용"). 위반은
    app.rules.ppe_violation_log로 위치 체이닝해 **연속 2회 확정**돼야만 빨간 점선
    박스+"~미착용" 라벨을 그린다(1회차 오검출은 그냥 기본 박스로 둔다).
  화재 감지(app.rules.alarm_trigger, 연속 2회 확정) 이후: PPE 판정은 완전히 건너뛰고,
    화면에 남아있는(관측되는) 사람은 초록 박스. 2차 확인(situation_probe)이 "쓰러진
    사람"/"연기에 둘러싸인 사람"으로 분류한 사람만 빨간 박스로 바뀐다.

모델은 N프레임마다 한 번만 부르고(sample_every), 그 결과를 다음 프레임들에도 그대로 그려서
출력 영상은 항상 원본 프레임을 전부 담아 매끄럽게 재생된다.

사용 예:
    python -m backend.scripts.annotate_pipeline_video \
        --video LastSight_Demo.mp4 --out backend/data/annotate_jobs/pipeline_demo.mp4 \
        --sample-every 24 --request-interval-sec 1.2
"""

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 import 루트로

from app.core.bdai_client import get_bdai_client
from app.inference import detector, fire_detector, situation_probe
from app.pipeline import scenario_runner
from app.rules import alarm_trigger, ppe_violation_log
from app.rules import zone as zone_rules
from app.rules.ppe_compliance import ComplianceState, evaluate_ppe_compliance, stabilize_display

VIDEO_CAMERA_ID = "pipeline-demo"

FIRE_COLOR = {"fire": (44, 65, 232), "smoke": (191, 143, 156)}
NORMAL_PERSON_COLOR = (180, 180, 180)
VIOLATION_COLOR = (45, 45, 255)  # 빨간 점선 — PPE 미착용 확정
OBSERVED_COLOR = (90, 200, 90)  # 초록 — 화재 후 관측 중
CONCERN_COLOR = (45, 45, 255)  # 빨간 실선 — 2차 확인에서 우려 상황 확정


def _encode(frame) -> str:
    ok, buf = cv2.imencode(".jpg", frame)
    import base64

    return base64.b64encode(buf).decode("ascii")


def _detect_person_only(frame, confidence: float) -> list[tuple[float, float, float, float]]:
    """비상시엔 helmet/vest가 필요 없으므로 ZERO에 person 프롬프트만 물어 호출을 아낀다."""
    client = get_bdai_client()
    result = client.foundation.predict(
        "zero", image={"image_b64": _encode(frame)}, text_prompts=["person"], confidence=confidence
    )
    return [(p.geometry.x, p.geometry.y, p.geometry.x + p.geometry.w, p.geometry.y + p.geometry.h) for p in result.predictions]


def draw_box(frame, bbox, color, label=None, dashed=False, thickness=2):
    """dashed=True(PPE 위반)면 라벨을 박스 아래에, 그 외(관측중/우려 상황)는 라벨을 박스 위에 그린다."""
    x1, y1, x2, y2 = map(int, bbox)
    if dashed:
        step = 14
        for x in range(x1, x2, step * 2):
            cv2.line(frame, (x, y1), (min(x + step, x2), y1), color, thickness)
            cv2.line(frame, (x, y2), (min(x + step, x2), y2), color, thickness)
        for y in range(y1, y2, step * 2):
            cv2.line(frame, (x1, y), (x1, min(y + step, y2)), color, thickness)
            cv2.line(frame, (x2, y), (x2, min(y + step, y2)), color, thickness)
    else:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

    if not label:
        return
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    if dashed:
        bg_top, text_y = y2, y2 + th + 4
    else:
        bg_top, text_y = max(0, y1 - th - 8), max(12, y1 - 6)
    cv2.rectangle(frame, (x1, bg_top), (x1 + tw + 4, bg_top + th + 8), color, -1)
    cv2.putText(frame, label, (x1 + 2, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--start-sec", type=float, default=0.0, help="원본 영상에서 이 시각부터 처리 시작")
    parser.add_argument("--end-sec", type=float, default=None, help="원본 영상에서 이 시각까지만 처리(생략 시 끝까지 또는 --max-frames까지)")
    parser.add_argument("--sample-every", type=int, default=16)  # ~0.67초 간격(기존 24=~1초) — 걷는 사람 체이닝 안정성 향상
    parser.add_argument("--person-confidence", type=float, default=0.3)
    parser.add_argument("--fire-confidence", type=float, default=0.3)
    parser.add_argument("--probe-confidence", type=float, default=0.3)
    parser.add_argument("--request-interval-sec", type=float, default=1.2)
    args = parser.parse_args()

    scenario_runner._register_demo_zone_map()  # zone_rules.which_zone이 A/B구역을 알 수 있게

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {args.video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start_frame = round(args.start_sec * src_fps)
    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    max_frames = args.max_frames
    if args.end_sec is not None:
        duration_frames = round((args.end_sec - args.start_sec) * src_fps)
        max_frames = duration_frames if max_frames is None else min(max_frames, duration_frames)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), src_fps, (w, h))

    sim_start = datetime(2026, 1, 1, tzinfo=UTC)
    fire_window: list = []
    fire_triggered = False

    # 화면에 그릴, "직전 샘플에서 계산해 둔" 상태 — 다음 프레임들에도 그대로 유지해서 재생
    last_fire_dets: list = []
    last_boxes: list[tuple] = []  # (bbox, color, label, dashed)

    frame_idx = 0
    written = 0
    detect_calls = 0
    fire_calls = 0
    probe_calls = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_idx % args.sample_every == 0:
            if detect_calls + fire_calls + probe_calls > 0:
                time.sleep(args.request_interval_sec)
            sample_idx = frame_idx // args.sample_every
            now = sim_start + timedelta(seconds=sample_idx * (args.sample_every / src_fps))

            fire_dets = fire_detector.detect(frame, confidence_threshold=args.fire_confidence)
            fire_calls += 1
            fire_window.append(fire_dets)
            fire_window = fire_window[-scenario_runner.FIRE_CONSECUTIVE_REQUIRED :]
            last_fire_dets = fire_dets

            if not fire_triggered:
                alert = alarm_trigger.evaluate(
                    VIDEO_CAMERA_ID,
                    fire_window,
                    confidence_threshold=scenario_runner.FIRE_CONFIDENCE_THRESHOLD,
                    consecutive_required=scenario_runner.FIRE_CONSECUTIVE_REQUIRED,
                )
                if alert is not None:
                    fire_triggered = True
                    print(f"    🔥 화재경보 발생 (t={now.isoformat()}, 신뢰도 {alert.confidence:.2f}) — 이후 PPE 판정 중단, 관측 모드로 전환")

            new_boxes: list[tuple] = []

            if not fire_triggered:
                time.sleep(args.request_interval_sec)
                person_dets = detector.detect(frame, confidence_threshold=args.person_confidence)
                detect_calls += 1
                person_boxes = [d.bbox_xyxy for d in person_dets if d.object_class.value == "person"]
                helmet_boxes = [d.bbox_xyxy for d in person_dets if d.object_class.value == "helmet"]
                vest_boxes = [d.bbox_xyxy for d in person_dets if d.object_class.value == "vest"]

                time.sleep(args.request_interval_sec)
                head_boxes, upper_body_boxes = detector.detect_head_upper_body(frame, args.person_confidence)
                detect_calls += 1

                for box in person_boxes:
                    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                    zone_id = zone_rules.which_zone(scenario_runner.DEMO_CAMERA_ID, (cx, cy)) or "미분류"

                    compliance = evaluate_ppe_compliance(
                        box, head_boxes=head_boxes, helmet_boxes=helmet_boxes,
                        vest_boxes=vest_boxes, upper_body_boxes=upper_body_boxes,
                    )
                    # 대칭 히스테리시스 — 미착용 확정도, 다시 착용으로 돌아오는 것도 같은 위치에서
                    # 연속 2회 나와야 화면 표시가 바뀐다.
                    display_helmet = stabilize_display(VIDEO_CAMERA_ID, zone=zone_id, ppe_type="helmet", raw_state=compliance.helmet, bbox_xyxy=box, now=now)
                    display_vest = stabilize_display(VIDEO_CAMERA_ID, zone=zone_id, ppe_type="vest", raw_state=compliance.vest, bbox_xyxy=box, now=now)
                    violations = [name for name, state in (("helmet", display_helmet), ("vest", display_vest)) if state == ComplianceState.NOT_WORN]

                    if violations:
                        logged = ppe_violation_log.record_if_new_violation(
                            VIDEO_CAMERA_ID, zone=zone_id, violations=violations, now_iso=now.isoformat(),
                            frame_path=None, bbox_xyxy=box, confidence=None,
                        )
                        label = ppe_violation_log.format_violation_text(violations)
                        new_boxes.append((box, VIOLATION_COLOR, label, True))
                        if logged:
                            print(f"    [t={now.isoformat()}] {zone_id} — {label} 확정(연속 2회)")
                    else:
                        new_boxes.append((box, NORMAL_PERSON_COLOR, None, False))
                print(f"[샘플 {sample_idx}] 프레임 {frame_idx} — person {len(person_boxes)}건, head {len(head_boxes)}건, upper_body {len(upper_body_boxes)}건, fire/smoke {len(fire_dets)}건 (평상시)")
            else:
                time.sleep(args.request_interval_sec)
                person_boxes = _detect_person_only(frame, args.person_confidence)
                detect_calls += 1

                concern_by_idx: dict[int, str] = {}
                if person_boxes:
                    time.sleep(args.request_interval_sec)
                    workers_by_zone: dict[str, list[tuple[str, tuple]]] = {}
                    for i, box in enumerate(person_boxes):
                        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                        zone_id = zone_rules.which_zone(scenario_runner.DEMO_CAMERA_ID, (cx, cy)) or "미분류"
                        workers_by_zone.setdefault(zone_id, []).append((str(i), box))
                    _, matched_category = situation_probe.probe_zone_situation(frame, workers_by_zone, confidence=args.probe_confidence)
                    probe_calls += 1
                    concern_by_idx = {int(tid): cat for tid, cat in matched_category.items()}

                for i, box in enumerate(person_boxes):
                    category = concern_by_idx.get(i)
                    if category:
                        new_boxes.append((box, CONCERN_COLOR, category, False))
                    else:
                        new_boxes.append((box, OBSERVED_COLOR, "관측중", False))
                print(f"[샘플 {sample_idx}] 프레임 {frame_idx} — person {len(person_boxes)}건, fire/smoke {len(fire_dets)}건 (비상시, 우려 {len(concern_by_idx)}명)")

            last_boxes = new_boxes

        for d in last_fire_dets:
            x1, y1, x2, y2 = map(int, d.bbox_xyxy)
            color = FIRE_COLOR.get(d.object_class.value, (0, 0, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{d.object_class.value} {d.confidence:.2f}"
            cv2.putText(frame, label, (x1 + 2, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        for box, color, label, dashed in last_boxes:
            draw_box(frame, box, color, label=label, dashed=dashed)

        writer.write(frame)
        written += 1
        if max_frames and written >= max_frames:
            break
        frame_idx += 1

    cap.release()
    writer.release()
    print(f"\n완료: {written}프레임({written / src_fps:.1f}초) → {out_path}")
    print(f"호출 횟수 — person/PPE: {detect_calls}, fire: {fire_calls}, 2차확인: {probe_calls}")


if __name__ == "__main__":
    main()
