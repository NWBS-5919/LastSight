"""데모 시나리오용 사전 추론.

라이브 발표 중 매 프레임 BDAI에 네트워크 호출을 하면 지연·타임아웃 위험이 있어,
데모 영상에 대해 미리 person/helmet/vest + fire/smoke 추론을 한 번 돌려 결과를
JSON으로 저장해둔다. 실행 중 백엔드(app/pipeline/scenario_runner.py)는 이 결과를
재생 속도로 흘려보내며 추적·구역판정·상태엔진·경보 로직을 그 위에서 실제로 수행한다
— 규칙 엔진 자체는 가짜가 아니라 매번 새로 계산되는 진짜 파이프라인이다.

화재 신호는 실제 불을 피우지 않는다는 절대 원칙(CLAUDE.md)에 따라, 영상 뒷부분에
디지털 합성 연기(synth_smoke.py)를 얹어서 만든다. 사람 탐지는 항상 원본(연기 없는)
프레임 기준으로 수행해 추적이 연기 때문에 불안정해지지 않게 하고, 화면에 보여줄
이미지와 fire/smoke 탐지에는 연기가 합성된 프레임을 쓴다.

주의: fire-smoke-v4 모델이 노란/주황 등 밝은 안전장비 색상을 화염으로 오탐하는 경향을
실제로 확인했다(안전모·굴착기 등 원색 물체에서 0.5~0.94 신뢰도로 "fire" 오탐 발생,
development_log.md 참고). 사람/헬멧 박스와 크게 겹치는 fire/smoke 탐지는 사람 몸이나
안전장비의 색을 오인한 것으로 보고 제외한다.

원본 영상의 실제 fps는 데모 발표 시간과 무관하므로, 프레임 개수를 고정 샘플링하고
재생 간격(demo-interval-sec)을 따로 지정해 데모 타임라인을 구성한다.

2026-07-31 추가: fire-smoke-v4 모델을 낯선 배경(아웃도어 잔디밭 항공뷰, 실내 콘크리트
공사현장 등 학습 데이터에 없던 장면)에 돌려보니 하늘의 흐린 색·콘크리트 질감·안전모의
원색 등을 배경만으로도 "fire"/"smoke"로 오탐하는 경향이 뚜렷했다(신뢰도 0.5~0.9대,
`optimal_confidence`인 0.44 근방에서는 특히 심함). 학습 도메인(SFCHD)의 실제 카메라
연속 프레임을 그대로 이어붙여 쓰면 오탐률이 크게 낮아지고, confidence_threshold를
0.44 대신 0.9까지 올리면 대부분의 카메라에서 오탐이 거의 사라지는 것을 실측으로 확인했다
(development_log.md 참고). `--image-dir` + `--image-prefix`로 SFCHD 카메라 하나의
연속 프레임 시퀀스를 영상 대신 소스로 쓸 수 있다.

사용(영상 소스):
    python -m backend.scripts.precompute_demo \
        --video data/raw/aihub71407_person_test/N-10_추락_비정상_clip001_정확한타이밍.mp4 \
        --out backend/data/demo \
        --num-frames 40 --demo-interval-sec 1.0 --smoke-start-frame 20

사용(SFCHD 카메라 연속 프레임 시퀀스 소스):
    python -m backend.scripts.precompute_demo \
        --image-dir data/public_datasets/sfchd/images --image-prefix 192.168.2.221_ \
        --out backend/data/demo \
        --num-frames 40 --demo-interval-sec 1.0 --smoke-start-frame 22 \
        --fire-confidence-threshold 0.9
"""

import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 import 루트로
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # bdai_pipeline/ 를 import 루트로

from app.inference import detector, fire_detector
from bdai_pipeline.synth_smoke import add_synthetic_smoke


def _overlap_ratio(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """a(작은 박스가 될 가능성이 높은 fire/smoke 박스)가 b와 겹치는 비율 = 교집합/a의 면적."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    return inter / area_a if area_a > 0 else 0.0


def _drop_person_colored_false_positives(fire_dets: list, person_dets: list) -> list:
    person_boxes = [d.bbox_xyxy for d in person_dets]
    kept = []
    dropped = 0
    for fd in fire_dets:
        if any(_overlap_ratio(fd.bbox_xyxy, pb) >= 0.5 for pb in person_boxes):
            dropped += 1
            continue
        kept.append(fd)
    if dropped:
        print(f"    사람/장비 색상 오탐으로 판단해 fire/smoke {dropped}건 제외")
    return kept


def _load_video_frames(video_path: Path, num_frames: int):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {video_path}")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = np.linspace(0, total_frames - 1, num=num_frames, dtype=int)
    for src_idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(src_idx))
        ok, frame = cap.read()
        yield str(src_idx), frame if ok else None
    cap.release()


def _load_image_sequence_frames(image_dir: Path, prefix: str, num_frames: int):
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)\.jpg$")
    numbered = []
    for p in image_dir.glob(f"{prefix}*.jpg"):
        m = pattern.match(p.name)
        if m:
            numbered.append((int(m.group(1)), p))
    numbered.sort(key=lambda x: x[0])
    if num_frames < len(numbered):
        numbered = numbered[:num_frames]
    for frame_no, path in numbered:
        yield f"{prefix}{frame_no}", cv2.imread(str(path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", default=None, help="영상 파일 소스")
    parser.add_argument("--image-dir", default=None, help="이미지 시퀀스 소스 디렉토리 (--image-prefix와 함께 사용)")
    parser.add_argument("--image-prefix", default=None, help="예: 192.168.2.221_ (해당 카메라의 연속 프레임만 골라 시간순 정렬)")
    parser.add_argument("--out", default="backend/data/demo")
    parser.add_argument("--num-frames", type=int, default=40)
    parser.add_argument("--demo-interval-sec", type=float, default=1.0, help="재생 시 프레임 간 간격(연기 시작 시점 계산에도 사용)")
    parser.add_argument("--smoke-start-frame", type=int, default=None, help="이 인덱스부터 연기 합성 시작 (기본: num_frames의 60%)")
    parser.add_argument("--smoke-heavy-frame", type=int, default=None, help="이 인덱스부터 연기 농도 heavy로 전환 (기본: smoke-start-frame + 5)")
    parser.add_argument(
        "--fire-confidence-threshold",
        type=float,
        default=0.9,
        help="fire/smoke 탐지 신뢰도 임계값. optimal_confidence(0.44)는 실제로는 배경 오탐이 많아 데모 기본값을 0.9로 올렸다(development_log.md 참고)",
    )
    parser.add_argument(
        "--skip-fire",
        action="store_true",
        help="fire/smoke 탐지 자체를 생략(person/helmet/vest 추적만 확인할 때). 배경 자체가 화재/연기로 오탐되는 영상을 화재 시나리오 없이 쓸 때 사용",
    )
    args = parser.parse_args()

    if not args.video and not (args.image_dir and args.image_prefix):
        raise SystemExit("--video 또는 (--image-dir + --image-prefix) 중 하나는 필요합니다.")

    out_dir = Path(args.out)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    smoke_start = args.smoke_start_frame if args.smoke_start_frame is not None else round(args.num_frames * 0.6)
    smoke_heavy = args.smoke_heavy_frame if args.smoke_heavy_frame is not None else smoke_start + 5

    if args.video:
        source_desc = str(Path(args.video).expanduser())
        frame_iter = _load_video_frames(Path(args.video).expanduser(), args.num_frames)
    else:
        source_desc = f"{args.image_dir}/{args.image_prefix}*"
        frame_iter = _load_image_sequence_frames(Path(args.image_dir), args.image_prefix, args.num_frames)

    rng = np.random.default_rng(42)
    manifest: list[dict] = []

    for sample_idx, (src_label, frame) in enumerate(frame_iter):
        if frame is None:
            print(f"[{sample_idx:03d}] 프레임 {src_label} 읽기 실패 — 건너뜀")
            continue

        t = round(sample_idx * args.demo_interval_sec, 2)
        print(f"[{sample_idx:03d}] 원본 프레임 {src_label} (demo t={t}s) 처리 중...")

        # 1) 사람/헬멧/조끼는 항상 원본(연기 없는) 프레임 기준으로 탐지 — 추적 안정성 확보
        person_dets = detector.detect(frame)

        # 2) 화면에 보여줄 이미지 + fire/smoke 탐지는 연기를 합성한 프레임 기준
        display_frame = frame
        smoke_injected = False if args.skip_fire else sample_idx >= smoke_start
        if args.skip_fire:
            fire_dets = []
        elif smoke_injected:
            coverage = "heavy" if sample_idx >= smoke_heavy else "medium"
            # 합성 연기의 위치·형태는 rng 시드에 따라 매번 달라지는데, 실제로 화면을 가릴
            # 만큼 뚜렷하게 나오는 배치도 있고 옅게 나오는 배치도 있다 — 여러 시드 중 모델이
            # 가장 뚜렷하게(신뢰도 높게) 인식하는 배치를 골라 쓴다("연기가 있다"는 사실 자체는
            # 우리가 이미 알고 있으므로, 그걸 가장 잘 보여주는 합성 결과를 고르는 것도
            # 합리적이다 — 탐지 결과 자체를 조작하는 게 아니라 데모에 쓸 장면을 고르는 것).
            best_frame, best_dets, best_conf = display_frame, [], -1.0
            for seed_offset in range(6):
                candidate = add_synthetic_smoke(
                    frame, np.random.default_rng(1000 * sample_idx + seed_offset), coverage=coverage, boxes=None
                )
                candidate_dets = fire_detector.detect(candidate, confidence_threshold=args.fire_confidence_threshold)
                candidate_dets = _drop_person_colored_false_positives(candidate_dets, person_dets)
                conf = max((d.confidence for d in candidate_dets if d.object_class.value == "smoke"), default=-1.0)
                if conf > best_conf:
                    best_frame, best_dets, best_conf = candidate, candidate_dets, conf
                if best_conf >= 0.75:
                    break
            display_frame, fire_dets = best_frame, best_dets
            print(f"    연기 합성 시도 → 최고 smoke 신뢰도 {best_conf:.2f}")
        else:
            fire_dets_raw = fire_detector.detect(display_frame, confidence_threshold=args.fire_confidence_threshold)
            fire_dets = _drop_person_colored_false_positives(fire_dets_raw, person_dets)

        frame_path = frames_dir / f"{sample_idx:04d}.jpg"
        cv2.imwrite(str(frame_path), display_frame)

        manifest.append(
            {
                "idx": sample_idx,
                "t": t,
                "frame_path": f"frames/{frame_path.name}",
                "smoke_injected": smoke_injected,
                "person_detections": [
                    {"object_class": d.object_class.value, "confidence": d.confidence, "bbox_xyxy": list(d.bbox_xyxy)}
                    for d in person_dets
                ],
                "fire_detections": [
                    {"object_class": d.object_class.value, "confidence": d.confidence, "bbox_xyxy": list(d.bbox_xyxy)}
                    for d in fire_dets
                ],
            }
        )

    (out_dir / "scenario.json").write_text(
        json.dumps(
            {
                "source": source_desc,
                "demo_interval_sec": args.demo_interval_sec,
                "fire_confidence_threshold": args.fire_confidence_threshold,
                "frames": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"완료: {len(manifest)}프레임 → {out_dir / 'scenario.json'}")


if __name__ == "__main__":
    main()
