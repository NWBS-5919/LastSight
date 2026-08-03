"""영상에 fire/smoke 탐지 + (화재 구간에서) 2차 확인(situation_probe) 결과를 그려서
출력 영상으로 저장.

backend/scripts/annotate_video.py(PPE용)와 같은 패턴 — 대시보드·추적·규칙엔진과 무관하게,
화재/연기 탐지와 2차 확인이 실제로 잘 도는지 눈으로 빠르게 확인하기 위한 독립 스크립트.
모델은 N프레임마다 한 번만 부르고, 그 결과를 다음 N-1프레임에도 그대로 그려서 출력 영상은
항상 원본 프레임을 전부 담아 매끄럽게 재생되게 한다.

2차 확인(situation_probe.probe_zone_situation)은 fire/smoke가 잡힌 샘플에서만 추가로
불러 person 박스와 위치 매칭한 뒤, "쓰러진 사람"/"연기에 둘러싸인 사람"으로 분류된 사람은
빨간 점선 박스로 강조한다(프론트엔드 PPE 위반 표시와 같은 시각 언어).

사용 예:
    python -m backend.scripts.annotate_fire_video \
        --video LastSight_Demo.mp4 --out backend/data/annotate_jobs/fire_demo.mp4 \
        --sample-every 24 --request-interval-sec 1.2
"""

import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 import 루트로

from app.inference import detector, fire_detector, situation_probe

FIRE_COLOR = {
    "fire": (44, 65, 232),  # BGR, 프론트엔드 #e8412c 근사
    "smoke": (191, 143, 156),  # 프론트엔드 #9c8fbf 근사
}
PERSON_COLOR = (200, 200, 200)
CONCERN_COLOR = (45, 45, 255)  # 프론트엔드 위반 표시 색(#ff2d2d) 근사


def draw_frame(frame, fire_dets, person_boxes, concern_by_idx: dict[int, str]):
    for d in fire_dets:
        x1, y1, x2, y2 = map(int, d.bbox_xyxy)
        color = FIRE_COLOR.get(d.object_class.value, (0, 0, 255))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{d.object_class.value} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    for i, box in enumerate(person_boxes):
        x1, y1, x2, y2 = map(int, box)
        category = concern_by_idx.get(i)
        if category:
            cv2.rectangle(frame, (x1, y1), (x2, y2), CONCERN_COLOR, 3)
            (tw, th), _ = cv2.getTextSize(category, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(frame, (x1, y2), (x1 + tw + 4, y2 + th + 8), CONCERN_COLOR, -1)
            cv2.putText(frame, category, (x1 + 2, y2 + th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        else:
            cv2.rectangle(frame, (x1, y1), (x2, y2), PERSON_COLOR, 1)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True, help="출력 영상 경로(.mp4)")
    parser.add_argument("--max-frames", type=int, default=None, help="처리할 최대 프레임 수(생략 시 전체)")
    parser.add_argument(
        "--sample-every", type=int, default=24,
        help="N프레임마다 모델을 1번 호출. 호출 사이 프레임에는 직전 결과를 그대로 그린다(출력 영상은 항상 전체 프레임을 매끄럽게 담음).",
    )
    parser.add_argument("--fire-confidence", type=float, default=0.3)
    parser.add_argument("--person-confidence", type=float, default=0.3)
    parser.add_argument("--probe-confidence", type=float, default=0.3)
    parser.add_argument(
        "--request-interval-sec", type=float, default=1.2,
        help="ZERO 호출 사이 대기 시간(초). person/fire/situation_probe를 한 샘플 안에서 여러 번 부르므로 호출 사이마다 쉰다.",
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {args.video}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), src_fps, (w, h))

    class_counts: dict[str, int] = {}
    frame_idx = 0
    written = 0
    detect_calls = 0
    probe_calls = 0
    last_fire_dets: list = []
    last_person_boxes: list = []
    last_concern: dict[int, str] = {}

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_idx % args.sample_every == 0:
            if detect_calls > 0:
                time.sleep(args.request_interval_sec)
            person_dets = detector.detect(frame, confidence_threshold=args.person_confidence)
            last_person_boxes = [d.bbox_xyxy for d in person_dets if d.object_class.value == "person"]

            time.sleep(args.request_interval_sec)
            fire_dets = fire_detector.detect(frame, confidence_threshold=args.fire_confidence)
            detect_calls += 1
            for d in fire_dets:
                class_counts[d.object_class.value] = class_counts.get(d.object_class.value, 0) + 1
            last_fire_dets = fire_dets

            last_concern = {}
            if fire_dets and last_person_boxes:
                time.sleep(args.request_interval_sec)
                workers_by_zone = {"현재화면": [(str(i), box) for i, box in enumerate(last_person_boxes)]}
                _, matched_category = situation_probe.probe_zone_situation(
                    frame, workers_by_zone, confidence=args.probe_confidence
                )
                probe_calls += 1
                last_concern = {int(tid): category for tid, category in matched_category.items()}
                if last_concern:
                    print(f"    2차 확인 → {last_concern}")

            print(f"[모델호출 {detect_calls}] 원본 프레임 {frame_idx} — person {len(last_person_boxes)}건, fire/smoke {len(fire_dets)}건")

        draw_frame(frame, last_fire_dets, last_person_boxes, last_concern)
        writer.write(frame)
        written += 1
        if args.max_frames and written >= args.max_frames:
            break
        frame_idx += 1

    cap.release()
    writer.release()
    print(f"\n완료: {written}프레임({written / src_fps:.1f}초) → {out_path}")
    print(f"모델 호출 {detect_calls}회(person+fire), 2차 확인 호출 {probe_calls}회")
    print("fire/smoke 탐지 총합:", class_counts)


if __name__ == "__main__":
    main()
