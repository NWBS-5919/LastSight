"""기존 라벨링된 PPE 이미지 중 helmet/vest 박스가 있는 이미지만 골라 색상 합성
(bdai_pipeline/synth_color_jitter.py)을 얹은 증강 복사본을 만들고, COCO 포맷으로 출력한다.

generate_motion_blur_augmented.py와 같은 패턴 — 박스 위치 자체는 안 바뀌므로 원본
바운딩박스 라벨을 그대로 재사용한다. 새로 만드는 건 "색 바꾼 이미지 파일"뿐, 새 라벨링
작업 없음.

development_log.md: 실측 결과 SFCHD가 helmet/vest 신호의 대부분을 차지하면서 색상도
편향돼 있었다(vest 66.8%가 파랑). 전체 이미지가 아니라 helmet/vest 박스가 실제로 있는
이미지만 대상으로 하고, --max-images로 표본을 제한해 과증강을 피한다.

사용 예:
    python -m bdai_pipeline.generate_color_jitter_augmented \
        --format yolo --source data/public_datasets/sfchd \
        --out data/public_datasets/sfchd-color-aug \
        --copies-per-image 1 --max-images 2000
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
    parser.add_argument("--max-images", type=int, default=None, help="helmet/vest 박스가 있는 이미지 중 서브샘플링 개수")
    parser.add_argument(
        "--target-classes",
        default="helmet,vest",
        help="색상 합성을 적용할 클래스명(쉼표구분, 원본 데이터셋 기준 class_name)",
    )
    args = parser.parse_args()

    target_classes = tuple(c.strip() for c in args.target_classes.split(",") if c.strip())

    all_images = parse(args.format, Path(args.source))
    images = [
        img
        for img in all_images
        if any(a.class_name in target_classes and a.geometry["type"] == "bbox" for a in img.annotations)
    ]
    print(f"전체 {len(all_images)}장 중 {target_classes} 박스가 있는 이미지 {len(images)}장")

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
        annotated_boxes = [
            (a.class_name, (a.geometry["x"], a.geometry["y"], a.geometry["w"], a.geometry["h"]))
            for a in img.annotations
            if a.geometry["type"] == "bbox"
        ]

        src = cv2.imread(str(img.path))
        if src is None:
            skipped += 1
            continue

        for copy_idx in range(args.copies_per_image):
            rng = np.random.default_rng(hash((img.filename, copy_idx)) % (2**32))
            from bdai_pipeline.synth_color_jitter import add_synthetic_color_jitter

            out_img = add_synthetic_color_jitter(src, rng, annotated_boxes, target_classes=target_classes)
            out_name = f"{img.path.stem}_cjit{copy_idx}.jpg"
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
