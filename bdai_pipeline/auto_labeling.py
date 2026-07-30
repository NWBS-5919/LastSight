"""Step 3→2 반복 — 배포된 모델로 새 데이터를 자동 라벨링.

담당: A. 실험이 진행되며 데이터를 추가로 확보할 때, 배포한 모델로 미리 라벨을
채워두고 사람이 검수만 하도록 해서 라벨링 속도를 높인다.

사용 예:
    python bdai_pipeline/auto_labeling.py --project lastsight --model-id <model_id> --confidence-threshold 0.5
"""

import argparse

from bdai_pipeline.client import get_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    args = parser.parse_args()

    client = get_client()  # noqa: F841
    # TODO: client로 자동 라벨링 설정(모델·임계값·클래스 매핑) 후 실행
    raise NotImplementedError


if __name__ == "__main__":
    main()
