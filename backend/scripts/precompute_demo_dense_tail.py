"""화재 이후 구간만 훨씬 촘촘하게 다시 사전계산해 scenario.json을 교체한다.

배경(development_log.md 참고): 화재 이후엔 사람들이 뛰어서 대피하는데, 추적(ByteTracker)이
1초 간격 샘플로는 그 이동 속도를 따라가지 못해 같은 사람이 계속 새 track_id로 잘못 분리되는
문제가 실측으로 확인됐다(idx=61~87 26프레임 만에 T0001~T0020, 20개 ID 생성). 임베딩 기반
재인식은 CLAUDE.md 원칙(얼굴인식·신원특정 금지)상 쓸 수 없으므로, 프레임 간 이동 거리 자체를
줄여(=위치 기반 매칭이 잘 통하게) 해결한다 — 화재 이전(평상시) 구간은 이 문제와 무관하므로
그대로 두고, 화재 전후 여유를 둔 DENSE_START_SEC부터 영상 끝까지만 훨씬 촘촘한 간격으로
다시 뽑아 기존 scenario.json의 뒷부분을 교체한다.

person/head-upper/fire 세 번의 ZERO 호출과 그 사이 sleep은 precompute_demo.py와 동일한
이유(공유 엔드포인트 rate limit)로 그대로 유지한다.
"""

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 import 루트로

from app.inference import detector, fire_detector
from precompute_demo import _drop_person_colored_false_positives  # noqa: E402

VIDEO_PATH = Path(__file__).resolve().parents[2] / "LastSight_Demo.mp4"
SCENARIO_PATH = Path(__file__).resolve().parents[1] / "data" / "demo" / "scenario.json"
FRAMES_DIR = Path(__file__).resolve().parents[1] / "data" / "demo" / "frames"

DENSE_START_SEC = 58.0  # 화재 트리거(원래 데이터 기준 t≈61s)보다 조금 앞서 여유를 둔다
DENSE_INTERVAL_SEC = 0.25  # 기존 1초 대비 4배
FIRE_CONFIDENCE_THRESHOLD = 0.3  # 기존 scenario.json 생성 시 값과 동일(원시 탐지는 넉넉히 저장)
REQUEST_INTERVAL_SEC = 1.5  # ZERO 호출 사이 대기(429 방지, precompute_demo.py와 동일)


def main() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    old_frames = scenario["frames"]

    kept = [f for f in old_frames if f["t"] < DENSE_START_SEC]
    print(f"기존 프레임 {len(old_frames)}개 중 t<{DENSE_START_SEC}s {len(kept)}개 유지")

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {VIDEO_PATH}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    print(f"원본 영상: fps={fps:.3f} total_frames={total_frames} duration={duration:.2f}s")

    sample_times = list(np.arange(DENSE_START_SEC, duration, DENSE_INTERVAL_SEC))
    print(f"새로 생성할 프레임 수: {len(sample_times)} (t={sample_times[0]:.2f}~{sample_times[-1]:.2f}s)")

    # 기존 frames/ 안의 이미지 중 이번에 버리는(t>=DENSE_START_SEC) 것들은 새 번호로 다시
    # 쓰여지므로 미리 정리한다 — 안 지우면 재인덱싱 후 안 쓰는 옛 이미지 파일이 남는다.
    keep_paths = {f["frame_path"] for f in kept}
    for p in FRAMES_DIR.glob("*.jpg"):
        rel = f"frames/{p.name}"
        if rel not in keep_paths:
            p.unlink()

    new_manifest: list[dict] = list(kept)
    next_idx = len(kept)

    for i, t in enumerate(sample_times):
        src_frame_idx = min(round(t * fps), total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, src_frame_idx)
        ok, frame = cap.read()
        if not ok:
            print(f"  t={t:.2f}s (src_frame={src_frame_idx}) 읽기 실패 — 건너뜀")
            continue

        idx = next_idx + i
        print(f"[{idx:04d}] t={t:.2f}s (src_frame={src_frame_idx}) 처리 중...")

        if idx > len(kept):
            time.sleep(REQUEST_INTERVAL_SEC)
        person_dets = detector.detect(frame)

        time.sleep(REQUEST_INTERVAL_SEC)
        head_boxes, upper_body_boxes = detector.detect_head_upper_body(frame)

        time.sleep(REQUEST_INTERVAL_SEC)
        fire_dets_raw = fire_detector.detect(frame, confidence_threshold=FIRE_CONFIDENCE_THRESHOLD)
        fire_dets = _drop_person_colored_false_positives(fire_dets_raw, person_dets)

        # 2026-08-04: precompute_demo_dense_head.py와 동일한 이유로 t(밀리초) 기반
        # 파일명을 쓴다 — head(t<DENSE_START_SEC)와 tail(t>=DENSE_START_SEC) 구간은 절대
        # 겹치지 않으므로, 로컬 idx 대신 t로 이름을 지으면 어느 스크립트를 어느 순서로
        # 다시 돌려도 파일명 충돌이 원천적으로 불가능하다.
        frame_path = FRAMES_DIR / f"t{round(t * 1000):07d}.jpg"
        cv2.imwrite(str(frame_path), frame)

        new_manifest.append(
            {
                "idx": idx,
                "t": round(float(t), 3),
                "frame_path": f"frames/{frame_path.name}",
                "smoke_injected": False,
                "person_detections": [
                    {"object_class": d.object_class.value, "confidence": d.confidence, "bbox_xyxy": list(d.bbox_xyxy)}
                    for d in person_dets
                ],
                "head_boxes": [list(b) for b in head_boxes],
                "upper_body_boxes": [list(b) for b in upper_body_boxes],
                "fire_detections": [
                    {"object_class": d.object_class.value, "confidence": d.confidence, "bbox_xyxy": list(d.bbox_xyxy)}
                    for d in fire_dets
                ],
            }
        )

    cap.release()

    # idx를 다시 매겨 0..N-1 연속으로 맞춘다(kept 구간은 이미 연속이므로 그대로).
    for i, f in enumerate(new_manifest):
        f["idx"] = i

    backup_path = SCENARIO_PATH.with_suffix(".json.bak")
    backup_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기존 scenario.json 백업: {backup_path}")

    scenario["frames"] = new_manifest
    SCENARIO_PATH.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: 총 {len(new_manifest)}프레임 (유지 {len(kept)} + 신규 {len(new_manifest) - len(kept)}) → {SCENARIO_PATH}")


if __name__ == "__main__":
    main()
