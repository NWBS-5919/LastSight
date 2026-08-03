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
import time
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
    parser.add_argument(
        "--sample-every", type=int, default=1,
        help="N프레임마다 모델을 1번 호출. 호출 사이 프레임에는 직전 탐지 결과를 그대로 그린다 "
        "(출력 영상은 항상 원본 프레임을 전부 담아 매끄럽게 재생된다. 기본 1=매프레임 호출).",
    )
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument(
        "--request-interval-sec", type=float, default=0.0,
        help="모델 호출 사이 대기 시간(초). ZERO는 공유 엔드포인트라 너무 자주 부르면 429(rate limit)가 난다.",
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {args.video}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 모델 호출은 sample_every프레임마다 하지만, 출력 영상엔 원본 프레임을 전부 그대로
    # 담는다 — 호출 사이 프레임은 직전 탐지 결과를 그대로 그려서 재생이 끊기지 않게 한다.
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), src_fps, (w, h))

    class_counts: dict[str, int] = {}
    frame_idx = 0
    written = 0
    detect_calls = 0
    last_dets: list = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % args.sample_every == 0:
            if detect_calls > 0 and args.request_interval_sec > 0:
                time.sleep(args.request_interval_sec)
            last_dets = detector.detect(frame, confidence_threshold=args.confidence)
            detect_calls += 1
            for d in last_dets:
                class_counts[d.object_class.value] = class_counts.get(d.object_class.value, 0) + 1
            print(f"[모델호출 {detect_calls}] 원본 프레임 {frame_idx} — 탐지 {len(last_dets)}건")
        draw_detections(frame, last_dets)
        writer.write(frame)
        written += 1
        if args.max_frames and written >= args.max_frames:
            break
        frame_idx += 1

    cap.release()
    writer.release()
    print(f"\n완료: {written}프레임({written / src_fps:.1f}초) → {out_path} (모델 호출 {detect_calls}회)")
    print("클래스별 탐지 총합:", class_counts)


if __name__ == "__main__":
    main()
