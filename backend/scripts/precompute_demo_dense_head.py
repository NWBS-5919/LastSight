"""평상시(화재 전, 0~58초) 구간을 촘촘하게 다시 사전계산해 scenario.json을 교체한다.

배경(development_log.md 참고): precompute_demo_dense_tail.py로 화재 이후 구간의 추적
오재부착 문제를 고쳤는데, 같은 원인(1초 샘플링보다 사람 걷는 속도가 빨라 위치 매칭이
끊김)이 화재 이전(평상시) PPE 판정에도 그대로 나타났다 — 위반 로그가 중복 기록되고,
화면 bbox가 확정→판정보류로 도로 튀는 현상이 실측으로 확인됨. 화재 이후 구간(이미
촘촘함, t>=DENSE_HEAD_END_SEC)은 그대로 두고, 그 앞부분만 다시 뽑아 scenario.json의
앞부분을 교체한다.

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

DENSE_HEAD_END_SEC = 58.0  # precompute_demo_dense_tail.py의 DENSE_START_SEC와 정확히 맞춰 이어붙인다
DENSE_INTERVAL_SEC = 0.5  # 기존 1초 대비 2배
FIRE_CONFIDENCE_THRESHOLD = 0.3  # 기존 scenario.json 생성 시 값과 동일(원시 탐지는 넉넉히 저장)
REQUEST_INTERVAL_SEC = 1.5  # ZERO 호출 사이 대기(429 방지, precompute_demo.py와 동일)


def main() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    old_frames = scenario["frames"]

    tail = [f for f in old_frames if f["t"] >= DENSE_HEAD_END_SEC]
    print(f"기존 프레임 {len(old_frames)}개 중 t>={DENSE_HEAD_END_SEC}s {len(tail)}개(화재 이후, 이미 촘촘함) 유지")

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {VIDEO_PATH}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"원본 영상: fps={fps:.3f} total_frames={total_frames}")

    sample_times = list(np.arange(0.0, DENSE_HEAD_END_SEC, DENSE_INTERVAL_SEC))
    print(f"새로 생성할 프레임 수: {len(sample_times)} (t={sample_times[0]:.2f}~{sample_times[-1]:.2f}s)")

    # 기존 frames/ 안의 이미지 중 이번에 버리는(t<DENSE_HEAD_END_SEC) 것들은 새 번호로
    # 다시 쓰여지므로 미리 정리한다 — 안 지우면 재인덱싱 후 안 쓰는 옛 이미지 파일이 남는다.
    keep_paths = {f["frame_path"] for f in tail}
    for p in FRAMES_DIR.glob("*.jpg"):
        rel = f"frames/{p.name}"
        if rel not in keep_paths:
            p.unlink()

    new_head: list[dict] = []

    for idx, t in enumerate(sample_times):
        src_frame_idx = min(round(t * fps), total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, src_frame_idx)
        ok, frame = cap.read()
        if not ok:
            print(f"  t={t:.2f}s (src_frame={src_frame_idx}) 읽기 실패 — 건너뜀")
            continue

        print(f"[{idx:04d}] t={t:.2f}s (src_frame={src_frame_idx}) 처리 중...")

        if idx > 0:
            time.sleep(REQUEST_INTERVAL_SEC)
        person_dets = detector.detect(frame)

        time.sleep(REQUEST_INTERVAL_SEC)
        head_boxes, upper_body_boxes = detector.detect_head_upper_body(frame)

        time.sleep(REQUEST_INTERVAL_SEC)
        fire_dets_raw = fire_detector.detect(frame, confidence_threshold=FIRE_CONFIDENCE_THRESHOLD)
        fire_dets = _drop_person_colored_false_positives(fire_dets_raw, person_dets)

        # 2026-08-04: 파일명을 로컬 idx(0부터 다시 시작)로 지으면, dense_tail이 이미
        # 써놓은 화재 이후 프레임 파일명(마찬가지로 로컬 idx 기반)과 범위가 겹쳐 서로
        # 덮어쓰는 사고가 실측으로 확인됐다(구조카드 초반 프레임이 실제와 다른 시점을
        # 보여주는 버그로 발견 — scripts/fix_frame_collisions.py 참고). t(초)는 head
        # (t<DENSE_HEAD_END_SEC)와 tail(t>=DENSE_HEAD_END_SEC) 구간이 절대 겹치지 않으므로,
        # 파일명을 t 기반(밀리초)으로 지으면 어느 스크립트를 어느 순서로 다시 돌려도 파일명
        # 충돌이 원천적으로 불가능하다.
        frame_path = FRAMES_DIR / f"t{round(t * 1000):07d}.jpg"
        cv2.imwrite(str(frame_path), frame)

        new_head.append(
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

    # 기존 tail 구간 프레임 이미지는 그대로 두되(파일명 안 바뀜), 전체 idx만
    # 0..N-1로 다시 매긴다. frame_path는 이미지 파일명과 묶여 있으므로 건드리지 않는다.
    new_manifest = new_head + tail
    for i, f in enumerate(new_manifest):
        f["idx"] = i

    backup_path = SCENARIO_PATH.with_suffix(".json.bak2")
    backup_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기존 scenario.json 백업: {backup_path}")

    scenario["frames"] = new_manifest
    SCENARIO_PATH.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: 총 {len(new_manifest)}프레임 (신규 {len(new_head)} + 유지 {len(tail)}) → {SCENARIO_PATH}")


if __name__ == "__main__":
    main()
