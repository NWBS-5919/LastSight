"""기존 polygon 라벨에서 bbox를 계산해 같은 인스턴스에 추가로 채워 넣는다.

segmentation에서 detection으로 학습 태스크를 바꾸면서, polygon으로만 존재하는
라벨(전체의 약 63%)이 detection 학습 통계에서 빠지는 문제를 해결하기 위한 스크립트.
polygon 점들의 최소/최대 좌표로 bbox를 계산하는 것뿐이라 정보 손실이 없다
(development_log.md 참고). 기존 polygon 라벨은 지우지 않고 bbox를 나란히 추가한다.

사용 예:
    python -m bdai_pipeline.backfill_bbox_from_polygon --project-id abad271f-68e8-4f63-a37a-f53e04b532d6
"""

import argparse
import json

from bdai_pipeline.client import get_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()

    client = get_client()

    rows = []
    skipped_no_points = 0
    for ann in client.annotations.list(args.project_id, type="polygon", include=["asset"]):
        xs: list[float] = []
        ys: list[float] = []
        for part in ann.geometry.polygons:
            for x, y in part.exterior:
                xs.append(x)
                ys.append(y)
        if not xs or not ys:
            skipped_no_points += 1
            continue
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        rows.append(
            {
                "class_id": str(ann.class_id),
                "type": "bbox",
                "filename": ann.asset.filename,
                "geometry": {"type": "bbox", "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
            }
        )

    print(f"polygon {len(rows) + skipped_no_points}개 중 bbox 계산 완료: {len(rows)}개 (점 없음 스킵: {skipped_no_points}개)")
    if not rows:
        print("백필할 게 없습니다.")
        return

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

    for i, batch in enumerate(batches, start=1):
        job = client.annotations.bulk_create(args.project_id, annotations=batch, source="imported")
        result = job.wait()
        print(f"배치 {i}/{len(batches)}: {len(batch)}개 → {result}")


if __name__ == "__main__":
    main()
