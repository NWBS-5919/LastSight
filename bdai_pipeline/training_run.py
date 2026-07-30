"""Step 3. BDAI 플랫폼에서 학습 실행 트리거.

로컬/Colab에서 학습한다면 이 스크립트는 사용하지 않아도 됨 (해커톤 규정상 감점 없음).
플랫폼에서 학습 시, 실험마다 experiments/logs/에 결과를 기록해 실험 계획
(docs/LastSight_AI_최종기획서.html 12번 섹션 1~10차)을 추적한다.

사용 예:
    python -m bdai_pipeline.training_run \
        --project-id ddc1dbe2-104c-4c4b-8741-68c5563733c7 \
        --version-id 2b89f582-6d31-45a5-acde-aa027ac5eb94 \
        --task detection --model rf-detr-nano --name ppe-baseline
"""

import argparse

from bdai_pipeline.client import get_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--task", choices=["detection", "segmentation"], required=True)
    parser.add_argument("--model", required=True, help="training.catalog()의 key (예: rf-detr-nano)")
    parser.add_argument("--name", required=True)
    parser.add_argument("--epochs", type=int, default=None, help="생략 시 카탈로그 기본값 사용")
    parser.add_argument("--wait", action="store_true", help="학습 완료까지 대기 (오래 걸릴 수 있음)")
    args = parser.parse_args()

    client = get_client()
    run = client.training.create_run(
        args.project_id,
        args.version_id,
        name=args.name,
        task=args.task,
        model=args.model,
        epochs=args.epochs,
    )
    print(f"학습 실행 시작: {run.name} ({run.id}) status={run.status}")

    if args.wait:
        run = client.training.wait_run(args.project_id, args.version_id, run.id)
        print(f"학습 완료: status={run.status}")
        metrics = client.training.metrics(args.project_id, args.version_id, run.id)
        for m in metrics:
            print(" ", m)


if __name__ == "__main__":
    main()
