"""Step 2 마무리 — 프로젝트의 현재 라벨 상태를 스냅샷(버전)으로 고정.

라벨이 없는 에셋은 기본적으로 제외한다 (--include-unannotated로 포함 가능).
스냅샷은 워크플로우(담당자/제출/승인) 상태와 무관하게 그 시점 어노테이션 데이터를 그대로 캡처한다.

사용 예:
    python -m bdai_pipeline.create_snapshot --project-id <id> --name v1-imported
"""

import argparse

from bdai_pipeline.client import get_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--include-unannotated", action="store_true")
    args = parser.parse_args()

    client = get_client()
    selection = None if args.include_unannotated else {"filter": {"annotated": True}}
    version = client.versions.create(args.project_id, name=args.name, selection=selection)
    print(f"스냅샷 생성 시작: {version.name} ({version.id}) status={version.status}")

    version = client.versions.wait_ready(args.project_id, version.id)
    print(f"스냅샷 준비 완료: status={version.status}, 에셋 {version.frozen_asset_count}개, 클래스 {version.frozen_class_count}개")


if __name__ == "__main__":
    main()
