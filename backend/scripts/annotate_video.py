"""영상에 person/helmet/vest 탐지 bbox를 그려서 출력 영상으로 저장.

대시보드·추적·규칙엔진과 무관하게, 배포된 PPE 모델(app.inference.detector)의 탐지 품질
자체만 눈으로 빠르게 확인하기 위한 독립 스크립트.

사용 예:
    python -m backend.scripts.annotate_video \
        --video data/raw/aihub71407_person_test/N-10_추락_비정상_clip001_4배속.mp4 \
        --out /tmp/annotated.mp4 --max-frames 60
"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 import 루트로

from app.inference import detector

COLOR = {
    "person": (255, 130, 60),  # BGR
    "helmet": (80, 200, 120),
    "vest": (0, 200, 230),
}


def draw_detections(frame, detections):
    for d in detections:
        x1, y1, x2, y2 = map(int, d.bbox_xyxy)
        color = COLOR.get(d.object_class.value, (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{d.object_class.value} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True, help="출력 영상 경로(.mp4)")
    parser.add_argument("--max-frames", type=int, default=None, help="처리할 최대 프레임 수(생략 시 전체)")
    parser.add_argument("--sample-every", type=int, default=1, help="N프레임마다 1장 처리(기본 1=전부)")
    parser.add_argument("--confidence", type=float, default=0.5)
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {args.video}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_fps = max(1.0, src_fps / args.sample_every)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), out_fps, (w, h))

    class_counts: dict[str, int] = {}
    frame_idx = 0
    written = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % args.sample_every == 0:
            dets = detector.detect(frame, confidence_threshold=args.confidence)
            for d in dets:
                class_counts[d.object_class.value] = class_counts.get(d.object_class.value, 0) + 1
            draw_detections(frame, dets)
            writer.write(frame)
            written += 1
            print(f"[{written}] 원본 프레임 {frame_idx} 처리 — 탐지 {len(dets)}건")
            if args.max_frames and written >= args.max_frames:
                break
        frame_idx += 1

    cap.release()
    writer.release()
    print(f"\n완료: {written}프레임 → {out_path}")
    print("클래스별 탐지 총합:", class_counts)


if __name__ == "__main__":
    main()
