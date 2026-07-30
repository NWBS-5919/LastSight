"""Step 2 마무리 — 라벨링·검수가 끝난 스냅샷을 로컬로 익스포트.

담당: A. BDAI에서 만든 스냅샷을 COCO 또는 YOLO 형식으로 받아 data/exports/에 저장.
Step 3(모델 학습)을 플랫폼 밖(로컬/Colab)에서 진행할 경우 이 스크립트로 데이터를 가져온다.

사용 예:
    python bdai_pipeline/export_snapshot.py --project lastsight --snapshot latest --format coco
"""

import argparse
from pathlib import Path

from bdai_pipeline.client import get_client

EXPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "exports"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--snapshot", default="latest")
    parser.add_argument("--format", choices=["coco", "yolo", "superb"], default="coco")
    args = parser.parse_args()

    client = get_client()  # noqa: F841
    # TODO: client로 스냅샷 조회 후 args.format 형식으로 EXPORT_DIR에 다운로드
    raise NotImplementedError


if __name__ == "__main__":
    main()
