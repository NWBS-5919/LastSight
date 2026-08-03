"""BDAI에 이미 반입한 5개 소스(COCO person, SFCHD 원본, SFCHD 연기합성, SHWD, Kaggle vest)를
로컬 YOLO 포맷 단일 데이터셋으로 병합한다. BDAI 스냅샷이 막혔을 때 로컬/Colab에서 바로
YOLO 학습을 시작할 수 있도록 하는 우회 경로.

클래스 순서(고정): person=0, helmet=1, vest=2, head=3, no_vest=4
각 소스의 class-map은 이번 세션에서 BDAI에 반입할 때 실제로 쓴 것과 동일하게 맞춘다.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2

from bdai_pipeline.import_public_dataset import parse

CLASSES = ["person", "helmet", "vest", "head", "no_vest"]
CLASS_INDEX = {name: i for i, name in enumerate(CLASSES)}

SOURCES = [
    {
        "name": "coco",
        "format": "coco",
        "source": "data/public_datasets/coco-person/images",
        "class_map": {"person": "person"},
    },
    {
        "name": "sfchd-orig",
        "format": "yolo",
        "source": "data/public_datasets/sfchd",
        "class_map": {
            "person": "person",
            "helmet": "helmet",
            "safety_clothes": "vest",
            "head": "head",
            "self_clothes": "no_vest",
        },
    },
    {
        "name": "sfchd-smoke",
        "format": "coco",
        "source": "data/public_datasets/sfchd-smoke-aug",
        "class_map": {
            "person": "person",
            "helmet": "helmet",
            "safety_clothes": "vest",
            "head": "head",
            "self_clothes": "no_vest",
        },
    },
    {
        "name": "shwd",
        "format": "voc",
        "source": "data/public_datasets/shwd-filtered",
        "class_map": {"hat": "helmet", "person": "head"},
        # BDAI에서는 no_helmet(=SHWD의 'person') 삭제 때 helmet('hat') 라벨이 하나도 없어
        # 무라벨이 된 이미지 2,021장을 통째로 삭제했다(5,240 -> 3,219장). 로컬 소스 폴더는
        # 그 삭제 전 원본 그대로라 hat이 하나도 없는 이미지를 이 필터로 똑같이 제외해야
        # head 라벨이 BDAI처럼 3,219장 분량(1,453개)으로 맞춰진다 — 안 걸러내면 69,227개
        # 규모로 되돌아가 no_helmet 때와 같은 클래스 불균형이 재발한다.
        "require_class": "hat",
    },
    {
        "name": "kaggle-vest",
        "format": "csv-voc",
        "source": "data/public_datasets/kaggle-safety-vests/images",
        "class_map": {"Safety Vest": "vest", "NO-Safety Vest": "no_vest"},
    },
]


def main() -> None:
    out_dir = Path("data/yolo_merged")
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    total_images = 0
    total_boxes = 0
    per_class_count = {c: 0 for c in CLASSES}

    for src in SOURCES:
        print(f"=== {src['name']} 처리 시작 ({src['format']}, {src['source']}) ===")
        images = parse(src["format"], Path(src["source"]))
        require_class = src.get("require_class")
        if require_class:
            before = len(images)
            images = [img for img in images if any(a.class_name == require_class for a in img.annotations)]
            print(f"  ({require_class!r} 라벨 없는 이미지 제외: {before} -> {len(images)}장)")
        class_map = src["class_map"]
        written = 0
        skipped_no_box = 0

        for img in images:
            lines = []
            for ann in img.annotations:
                if ann.geometry.get("type") != "bbox":
                    continue
                mapped = class_map.get(ann.class_name)
                if mapped is None:
                    continue
                cls_idx = CLASS_INDEX[mapped]
                g = ann.geometry
                lines.append((cls_idx, g["x"], g["y"], g["w"], g["h"]))

            if not lines:
                skipped_no_box += 1
                continue

            im = cv2.imread(str(img.path))
            if im is None:
                skipped_no_box += 1
                continue
            h, w = im.shape[:2]

            out_name = f"{src['name']}__{img.filename}"
            dst_img = images_dir / out_name
            if not dst_img.exists():
                os.symlink(img.path.resolve(), dst_img)

            label_lines = []
            for cls_idx, x, y, bw, bh in lines:
                cx = (x + bw / 2) / w
                cy = (y + bh / 2) / h
                nw = bw / w
                nh = bh / h
                label_lines.append(f"{cls_idx} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
                per_class_count[CLASSES[cls_idx]] += 1
                total_boxes += 1

            label_path = labels_dir / f"{Path(out_name).stem}.txt"
            label_path.write_text("\n".join(label_lines), encoding="utf-8")
            written += 1
            total_images += 1

        print(f"  -> {written}장 기록, 라벨 없어서 스킵 {skipped_no_box}장")

    (out_dir / "classes.txt").write_text("\n".join(CLASSES), encoding="utf-8")

    print("\n=== 병합 완료 ===")
    print("전체 이미지:", total_images)
    print("전체 박스:", total_boxes)
    for c, n in per_class_count.items():
        print(f"  {c}: {n}")
    print("출력 위치:", out_dir)


if __name__ == "__main__":
    main()
