"""공개 데이터셋(COCO / COCO-Segmentation / YOLO)을 BDAI에 업로드 + 라벨 반입.

두 단계로 나눠서 쓴다 (create_project_schema.py와 이유가 같음 — 프로젝트는 데이터셋에
에셋이 있어야 만들 수 있고, 어노테이션은 프로젝트의 class_id가 있어야 붙일 수 있다).

    # 1단계: 이미지만 업로드 (프로젝트 생성 전)
    python -m bdai_pipeline.import_public_dataset upload \
        --format coco --source data/public_datasets/construction-site-safety/train \
        --dataset-id <dataset_id>

    # (모든 소스 업로드 끝난 뒤) create_project_schema.py --step project 실행

    # 2단계: 라벨 반입 (프로젝트+클래스가 생긴 뒤)
    python -m bdai_pipeline.import_public_dataset annotate \
        --format coco --source data/public_datasets/construction-site-safety/train \
        --project-id <project_id> \
        --class-map '{"Person":"person","Hardhat":"helmet","Safety Vest":"vest"}'

지원 포맷:
  coco     : <source>/_annotations.coco.json (Roboflow COCO export, bbox)
  coco-seg : <source>/_annotations.coco.json (Roboflow COCO Segmentation export, polygon)
  yolo     : <source>/images/*.jpg + <source>/labels/*.txt + <source>/classes.txt (정규화 좌표)
  aihub176 : <source>/extracted_images/*.jpg + <source>/extracted_labels/*.json
             (AI Hub 176 "화재 발생 예측 데이터" 화재씬. class는 "01"~"04" 문자열이며
             --class-map으로 "01"/"02"/"03"(연기색상)→smoke, "04"(화염)→fire 매핑)

--max-images, --dedupe-suffix 로 증강본이 섞인 데이터셋(예: Fire and Smoke Segmentation)을
서브샘플링할 수 있다 (같은 원본의 증강 복사본이 train/valid에 나눠 들어가는 걸 방지).
"""

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bdai_pipeline.client import get_client


@dataclass
class ParsedAnnotation:
    class_name: str  # 원본 데이터셋의 클래스 이름 (class-map 적용 전)
    geometry: dict  # BDAI pixel-space geometry dict (type: bbox|polygon)


@dataclass
class ParsedImage:
    path: Path
    filename: str
    annotations: list[ParsedAnnotation]


def _dedupe_by_prefix(images: list[ParsedImage], suffix_marker: str) -> list[ParsedImage]:
    """Roboflow 증강본은 파일명이 `<원본이름>.rf.<해시>.jpg` 형태.
    marker(".rf.") 앞부분이 같으면 같은 원본에서 나온 증강본이므로 하나만 남긴다."""
    seen: set[str] = set()
    result = []
    for img in images:
        base = img.filename.split(suffix_marker)[0]
        if base in seen:
            continue
        seen.add(base)
        result.append(img)
    return result


def _parse_coco(source: Path, polygon: bool) -> list[ParsedImage]:
    ann_path = source / "_annotations.coco.json"
    data = json.loads(ann_path.read_text(encoding="utf-8"))

    categories = {c["id"]: c["name"] for c in data["categories"]}
    images_by_id = {im["id"]: im for im in data["images"]}

    per_image: dict[int, list[ParsedAnnotation]] = {im_id: [] for im_id in images_by_id}
    for ann in data["annotations"]:
        class_name = categories[ann["category_id"]]
        if polygon and ann.get("segmentation"):
            exteriors = []
            for seg in ann["segmentation"]:
                points = [[seg[i], seg[i + 1]] for i in range(0, len(seg), 2)]
                if len(points) >= 3:
                    exteriors.append({"exterior": points})
            if not exteriors:
                continue
            geometry = {"type": "polygon", "polygons": exteriors}
        else:
            x, y, w, h = ann["bbox"]
            geometry = {"type": "bbox", "x": x, "y": y, "w": w, "h": h}
        per_image[ann["image_id"]].append(ParsedAnnotation(class_name=class_name, geometry=geometry))

    result = []
    for im_id, im in images_by_id.items():
        path = source / im["file_name"]
        if not path.exists():
            continue
        result.append(ParsedImage(path=path, filename=path.name, annotations=per_image[im_id]))
    return result


def _parse_yolo(source: Path) -> list[ParsedImage]:
    classes = (source / "classes.txt").read_text(encoding="utf-8").splitlines()
    classes = [c.strip() for c in classes if c.strip()]

    images_dir = source / "images"
    labels_dir = source / "labels"

    result = []
    for img_path in sorted(images_dir.glob("*.jpg")):
        label_path = labels_dir / f"{img_path.stem}.txt"
        annotations = []
        if label_path.exists():
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            img_h, img_w = img.shape[:2]
            for line in label_path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) != 5:
                    continue
                cls_idx, cx, cy, w, h = int(parts[0]), *map(float, parts[1:])
                class_name = classes[cls_idx]
                px_w, px_h = w * img_w, h * img_h
                px_x, px_y = (cx * img_w) - px_w / 2, (cy * img_h) - px_h / 2
                annotations.append(
                    ParsedAnnotation(
                        class_name=class_name,
                        geometry={"type": "bbox", "x": px_x, "y": px_y, "w": px_w, "h": px_h},
                    )
                )
        result.append(ParsedImage(path=img_path, filename=img_path.name, annotations=annotations))
    return result


def _simplify_polygon(points: list[list[float]], epsilon_ratio: float = 0.002) -> list[list[float]]:
    """AI Hub 176 폴리곤은 크라우드 워커가 픽셀 단위로 촘촘히 찍어 점이 수백~수천 개다
    (완전 중복점도 흔함). Douglas-Peucker로 시각적 형태를 유지하면서 점 개수를 줄여
    bulk_create 요청 payload가 413(Request Entity Too Large)이 나지 않게 한다."""
    if len(points) < 4:
        return points
    arr = np.array(points, dtype=np.float32).reshape((-1, 1, 2))
    perimeter = cv2.arcLength(arr, True)
    epsilon = max(epsilon_ratio * perimeter, 1.0)
    approx = cv2.approxPolyDP(arr, epsilon, True)
    simplified = approx.reshape(-1, 2).tolist()
    return simplified if len(simplified) >= 3 else points


def _parse_aihub176(source: Path) -> list[ParsedImage]:
    images_dir = source / "extracted_images"
    labels_dir = source / "extracted_labels"

    result = []
    for img_path in sorted(images_dir.glob("*.jpg")):
        label_path = labels_dir / f"{img_path.stem}.json"
        if not label_path.exists():
            continue
        data = json.loads(label_path.read_text(encoding="utf-8"))
        annotations = []
        for ann in data.get("annotations", []):
            class_name = ann.get("class", "")
            geometry = None

            box = ann.get("box")
            if box and len(box) == 4:
                x1, y1, x2, y2 = box
                w, h = x2 - x1, y2 - y1
                if w > 0 and h > 0:
                    geometry = {"type": "bbox", "x": x1, "y": y1, "w": w, "h": h}

            if geometry is None:
                polygon = ann.get("polygon")
                if polygon:
                    # 원본 라벨 데이터에 [x,y]가 아닌 결손 점(예: [96] 처럼 좌표 1개만 있는 점)이
                    # 드물게 섞여 있어 걸러낸다.
                    polygon = [pt for pt in polygon if isinstance(pt, list) and len(pt) == 2]
                if polygon and len(polygon) >= 3:
                    geometry = {"type": "polygon", "polygons": [{"exterior": _simplify_polygon(polygon)}]}

            if geometry is None:
                continue
            annotations.append(ParsedAnnotation(class_name=class_name, geometry=geometry))
        result.append(ParsedImage(path=img_path, filename=img_path.name, annotations=annotations))
    return result


def parse(fmt: str, source: Path) -> list[ParsedImage]:
    if fmt == "coco":
        return _parse_coco(source, polygon=False)
    if fmt == "coco-seg":
        return _parse_coco(source, polygon=True)
    if fmt == "yolo":
        return _parse_yolo(source)
    if fmt == "aihub176":
        return _parse_aihub176(source)
    raise ValueError(f"알 수 없는 format: {fmt}")


def cmd_upload(args: argparse.Namespace) -> None:
    images = parse(args.format, Path(args.source))
    if args.dedupe_suffix:
        before = len(images)
        images = _dedupe_by_prefix(images, args.dedupe_suffix)
        print(f"증강본 중복 제거: {before}장 → {len(images)}장(원본 기준)")
    if args.max_images and len(images) > args.max_images:
        random.seed(42)
        images = random.sample(images, args.max_images)
        print(f"{args.max_images}장으로 서브샘플링")

    print(f"업로드할 이미지 {len(images)}장")
    client = get_client()
    results = client.assets.upload_paths(args.dataset_id, [im.path for im in images], concurrency=args.concurrency)
    failures = [r for r in results if not r.ok]
    print(f"완료: {len(results) - len(failures)}개 성공, {len(failures)}개 실패")
    for r in failures[:20]:
        print("  실패:", r.path, r.error)


def cmd_annotate(args: argparse.Namespace) -> None:
    class_map: dict[str, str] = json.loads(args.class_map)
    images = parse(args.format, Path(args.source))
    if args.dedupe_suffix:
        images = _dedupe_by_prefix(images, args.dedupe_suffix)
    if args.max_images and len(images) > args.max_images:
        random.seed(42)  # upload 때와 같은 시드 → 같은 서브셋
        images = random.sample(images, args.max_images)

    client = get_client()

    # 데이터셋에 에셋을 업로드해도 프로젝트 스코프에는 자동으로 안 들어간다(scope={"all": True}는
    # 프로젝트 생성 시점 스냅샷일 뿐, 이후 업로드분은 별도 등록 필요) — 안 하면 bulk_create가
    # "filename ... not found in this project's dataset"로 전부 조용히 실패한다(job 자체는
    # completed로 뜨지만 succeeded=0). 이미 등록된 에셋은 idempotent하게 skip되므로 매번 호출해도 안전.
    add_job = client.project_assets.bulk_add(args.project_id, filter={})
    add_result = add_job.wait()
    print(f"프로젝트 자산 스코프 동기화: {getattr(add_result, 'result_summary', add_result)}")

    classes = client.classes.list(args.project_id)
    class_id_by_name = {c.name: c.id for c in classes.classes}
    missing = {v for v in class_map.values() if v not in class_id_by_name}
    if missing:
        raise SystemExit(f"프로젝트에 없는 클래스: {missing} (create_project_schema.py를 먼저 실행했는지 확인)")

    rows = []
    skipped_unmapped = 0
    for img in images:
        for ann in img.annotations:
            mapped = class_map.get(ann.class_name)
            if mapped is None:
                skipped_unmapped += 1
                continue
            rows.append(
                {
                    "class_id": str(class_id_by_name[mapped]),
                    "type": ann.geometry["type"],
                    "filename": img.filename,
                    "geometry": ann.geometry,
                }
            )

    print(f"매핑 안 된 라벨 스킵: {skipped_unmapped}개, 반입할 라벨: {len(rows)}개")
    if args.skip_rows:
        rows = rows[args.skip_rows :]
        print(f"--skip-rows {args.skip_rows} 적용 → 이번에 반입할 라벨: {len(rows)}개")
    if not rows:
        print("반입할 라벨이 없습니다.")
        return

    # 폴리곤 점 개수가 라벨마다 크게 달라(수십~수천) 개수 기준 고정 배치는 413(Request
    # Entity Too Large)을 낼 수 있다. 직렬화 크기 누적 기준으로 배치를 나눈다.
    MAX_BATCH_BYTES = 2_000_000
    MAX_BATCH_ROWS = 1000
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_bytes = 0
    for row in rows:
        row_bytes = len(json.dumps(row).encode("utf-8"))
        if current and (current_bytes + row_bytes > MAX_BATCH_BYTES or len(current) >= MAX_BATCH_ROWS):
            batches.append(current)
            current, current_bytes = [], 0
        current.append(row)
        current_bytes += row_bytes
    if current:
        batches.append(current)

    processed = 0
    total_succeeded = 0
    total_failed = 0
    for batch_idx, batch in enumerate(batches, start=1):
        job = client.annotations.bulk_create(args.project_id, annotations=batch, source="imported")
        result = job.wait()
        processed += len(batch)
        succeeded = getattr(result, "succeeded", None)
        failed = getattr(result, "failed", None)
        total_succeeded += succeeded or 0
        total_failed += failed or 0
        print(
            f"  배치 {batch_idx}/{len(batches)} (원본 기준 {args.skip_rows + processed - len(batch)}~): "
            f"{len(batch)}개 시도 → 성공 {succeeded}, 실패 {failed}"
        )
        if failed:
            errors = (getattr(result, "result_summary", None) or {}).get("errors", [])
            for err in errors[:5]:
                print("    에러 샘플:", err)

    print(f"전체 결과: 성공 {total_succeeded}개, 실패 {total_failed}개 (반입 시도 {processed}개 중)")
    if total_failed:
        print("⚠️  일부 라벨 반입 실패 — 위 에러 샘플 확인 필요")
        time.sleep(2)  # 연속 호출로 인한 WAF/레이트리밋 방지


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["coco", "coco-seg", "yolo", "aihub176"], required=True)
    common.add_argument("--source", required=True)
    common.add_argument("--max-images", type=int, default=None)
    common.add_argument("--dedupe-suffix", default=None, help='예: ".rf." (Roboflow 증강본 중복 제거 기준)')

    p_upload = sub.add_parser("upload", parents=[common])
    p_upload.add_argument("--dataset-id", required=True)
    p_upload.add_argument("--concurrency", type=int, default=8)
    p_upload.set_defaults(func=cmd_upload)

    p_annotate = sub.add_parser("annotate", parents=[common])
    p_annotate.add_argument("--project-id", required=True)
    p_annotate.add_argument("--class-map", required=True, help='JSON, 예: \'{"Person":"person"}\'')
    p_annotate.add_argument("--skip-rows", type=int, default=0, help="앞에서부터 이미 반입된 행 수만큼 건너뛰기 (재시도용)")
    p_annotate.set_defaults(func=cmd_annotate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
