"""업로드된 영상에 person/helmet/vest bbox를 그려서 프레임 이미지로 저장.

LastSight 대시보드·추적·규칙엔진과 무관하게, 배포된 PPE 모델(app.inference.detector)의
탐지 품질 자체만 빠르게 눈으로 확인하기 위한 독립 기능. `backend/scripts/annotate_video.py`
(CLI용)와 같은 로직을 API에서 재사용할 수 있게 분리했다.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2

from app.inference import detector

JOBS_DIR = Path(__file__).resolve().parents[2] / "data" / "annotate_jobs"

COLOR = {
    "person": (255, 130, 60),  # BGR
    "helmet": (80, 200, 120),
    "vest": (0, 200, 230),
}


def _draw_detections(frame, detections):
    for d in detections:
        x1, y1, x2, y2 = map(int, d.bbox_xyxy)
        color = COLOR.get(d.object_class.value, (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{d.object_class.value} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return frame


def annotate_video(
    video_path: Path,
    *,
    sample_every: int = 4,
    max_frames: int = 80,
    confidence: float = 0.5,
) -> dict:
    """video_path를 처리해 프레임마다 bbox를 그린 jpg를 저장하고, 프레임 URL 목록 등을 반환."""
    job_id = uuid.uuid4().hex[:12]
    out_dir = JOBS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0

    class_counts: dict[str, int] = {}
    frame_idx = 0
    written = 0
    frame_files: list[str] = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % sample_every == 0:
            dets = detector.detect(frame, confidence_threshold=confidence)
            for d in dets:
                class_counts[d.object_class.value] = class_counts.get(d.object_class.value, 0) + 1
            _draw_detections(frame, dets)
            fname = f"{written:04d}.jpg"
            cv2.imwrite(str(out_dir / fname), frame)
            frame_files.append(fname)
            written += 1
            if written >= max_frames:
                break
        frame_idx += 1

    cap.release()

    return {
        "job_id": job_id,
        "frame_count": written,
        "playback_fps": max(1.0, src_fps / sample_every),
        "frame_files": frame_files,
        "class_counts": class_counts,
    }
