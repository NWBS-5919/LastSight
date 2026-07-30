"""기존 라벨링된 PPE 이미지에 합성 연기(bdai_pipeline/synth_smoke.py)를 얹어
증강 복사본을 만들고, COCO 포맷으로 출력한다.

핵심: 사람 위치 자체는 안 바뀌므로 원본 바운딩박스 라벨을 그대로 재사용한다.
새로 만드는 건 "연기 얹은 이미지 파일"뿐 — 새 라벨링 작업 없음.

출력 폴더는 --format coco 그대로 import_public_dataset.py의 upload/annotate에
넘길 수 있는 형태(<out>/_annotations.coco.json + 이미지)라, 기존 업로드 파이프라인을
그대로 재사용한다. 원본 이미지는 이미 BDAI에 올라가 있으므로 출력물에는 증강본만 담는다.

사용 예:
    python -m bdai_pipeline.generate_smoke_augmented \
        --format coco --source data/public_datasets/construction-site-safety/train \
        --out data/public_datasets/construction-site-safety-smoke-aug \
        --copies-per-image 1

    python -m bdai_pipeline.generate_smoke_augmented \
        --format yolo --source data/public_datasets/sfchd \
        --out data/public_datasets/sfchd-smoke-aug \
        --copies-per-image 1 --max-images 4000
"""

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np

from bdai_pipeline.import_public_dataset import parse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["coco", "yolo"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--copies-per-image", type=int, default=1)
    parser.add_argument("--max-images", type=int, default=None, help="원본 이미지 서브샘플링 (증강 전 기준)")
    args = parser.parse_args()

    images = parse(args.format, Path(args.source))
    if args.max_images and len(images) > args.max_images:
        random.seed(42)
        images = random.sample(images, args.max_images)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    categories: dict[str, int] = {}
    coco_images = []
    coco_annotations = []
    next_image_id = 1
    next_ann_id = 1
    written = 0
    skipped = 0

    for img in images:
        boxes = [(a.geometry["x"], a.geometry["y"], a.geometry["w"], a.geometry["h"]) for a in img.annotations if a.geometry["type"] == "bbox"]

        src = cv2.imread(str(img.path))
        if src is None:
            skipped += 1
            continue

        for copy_idx in range(args.copies_per_image):
            rng = np.random.default_rng(hash((img.filename, copy_idx)) % (2**32))
            from bdai_pipeline.synth_smoke import add_synthetic_smoke

            out_img = add_synthetic_smoke(src, rng, coverage="random", boxes=boxes or None)
            out_name = f"{img.path.stem}_smoke{copy_idx}.jpg"
            cv2.imwrite(str(out_dir / out_name), out_img)

            h, w = out_img.shape[:2]
            coco_images.append({"id": next_image_id, "file_name": out_name, "width": w, "height": h})

            for ann in img.annotations:
                if ann.geometry["type"] != "bbox":
                    continue
                if ann.class_name not in categories:
                    categories[ann.class_name] = len(categories) + 1
                g = ann.geometry
                coco_annotations.append(
                    {
                        "id": next_ann_id,
                        "image_id": next_image_id,
                        "category_id": categories[ann.class_name],
                        "bbox": [g["x"], g["y"], g["w"], g["h"]],
                        "area": g["w"] * g["h"],
                        "iscrowd": 0,
                    }
                )
                next_ann_id += 1
            next_image_id += 1
            written += 1

    coco = {
        "images": coco_images,
        "annotations": coco_annotations,
        "categories": [{"id": cid, "name": name} for name, cid in categories.items()],
    }
    (out_dir / "_annotations.coco.json").write_text(json.dumps(coco, ensure_ascii=False), encoding="utf-8")

    print(f"원본 이미지 {len(images)}장 → 증강본 {written}장 생성 (읽기 실패로 건너뜀 {skipped}장)")
    print(f"출력: {out_dir} (format coco로 upload/annotate 그대로 사용 가능)")


if __name__ == "__main__":
    main()
