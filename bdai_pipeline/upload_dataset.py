"""Step 1. 데이터 선별 — 촬영 영상/이미지 또는 공개 데이터셋 이미지를 BDAI 데이터셋에 업로드.

담당: A. create_project_schema.py로 만든 데이터셋 id를 받아 폴더 안의 이미지를 올린다.

사용 예:
    python -m bdai_pipeline.upload_dataset --dataset-id <dataset_id> --source data/frames
"""

import argparse
from pathlib import Path

from bdai_pipeline.client import get_client

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--source", required=True, type=Path, help="업로드할 이미지가 들어있는 폴더 (하위 폴더 포함 탐색)")
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    paths = sorted(p for p in args.source.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    if not paths:
        raise SystemExit(f"{args.source} 아래에서 이미지 파일을 찾지 못했습니다 ({sorted(IMAGE_EXTS)}).")

    print(f"{len(paths)}개 파일 업로드 시작 → dataset {args.dataset_id}")

    client = get_client()
    results = client.assets.upload_paths(args.dataset_id, paths, concurrency=args.concurrency)

    failures = [r for r in results if not r.ok]
    print(f"완료: {len(results) - len(failures)}개 성공, {len(failures)}개 실패")
    for r in failures[:20]:
        print(f"  실패: {r.path} — {r.error}")
    print("참고: 성공(ok=True)은 S3 업로드 완료 시점 기준. 서버에서 asset row가 생성되기까지 비동기 지연이 있을 수 있으니, BDAI 데이터셋 화면에서 잠시 후 개수를 확인하세요.")


if __name__ == "__main__":
    main()
