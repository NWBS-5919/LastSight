"""Step 2. 데이터 구축 — 데이터셋과 프로젝트를 만들고 스키마(클래스·속성)를 등록.

담당: A. CLAUDE.md 4번 섹션(라벨 정의)과 backend/app/models/schemas.py의 ObjectClass 값을
그대로 반영해 BDAI 프로젝트 스키마를 만든다. person/helmet/vest는 자체 촬영, fire/smoke는
공개 데이터셋으로 학습하며 데이터 출처가 다르므로 별도 프로젝트로 분리한다 (CLAUDE.md 5번 Step 2).

BDAI는 프로젝트 스코프(scope={"all": True})를 데이터셋에 에셋이 최소 1개 이상 있어야 만들 수 있다
(빈 데이터셋으로 프로젝트를 만들면 "project scope is empty" 오류). 그래서 두 단계로 나눠서 쓴다.

사용 예:
    # 1) 데이터셋만 먼저 생성
    python -m bdai_pipeline.create_project_schema --target ppe --step dataset

    # 2) upload_dataset.py로 그 데이터셋에 이미지 업로드 (--dataset-id 위에서 나온 값)

    # 3) 이미지가 올라간 뒤 프로젝트+스키마 생성
    python -m bdai_pipeline.create_project_schema --target ppe --step project --dataset-id <dataset_id>

--target ppe  : person / helmet / vest
--target fire : fire / smoke
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.models.schemas import HelmetColor, VestColor, VisibilityLevel  # noqa: E402
from superb_ai.types.requests import (  # noqa: E402
    AttributeSpecParam,
    ClassificationConfigParam,
    ClassificationOptionParam,
    ClassSpecParam,
)

from bdai_pipeline.client import get_client  # noqa: E402


def _radio_attribute(name: str, values: list) -> AttributeSpecParam:
    return AttributeSpecParam(
        name=name,
        classification_config=ClassificationConfigParam(
            input_type="radio",
            options=[ClassificationOptionParam(value=v.value if hasattr(v, "value") else str(v), display=str(v)) for v in values],
            required=False,
        ),
    )


TOP_COLORS = ["검정", "흰색", "회색", "남색", "파랑", "빨강", "기타", "불명확"]


def ppe_classes() -> list[ClassSpecParam]:
    return [
        ClassSpecParam(
            name="person",
            allowed_types=["bbox"],
            attributes=[_radio_attribute("상의 색상", TOP_COLORS), _radio_attribute("가시성", list(VisibilityLevel))],
        ),
        ClassSpecParam(
            name="helmet",
            allowed_types=["bbox"],
            attributes=[_radio_attribute("안전모 색상", list(HelmetColor))],
        ),
        ClassSpecParam(
            name="vest",
            allowed_types=["bbox"],
            attributes=[_radio_attribute("안전조끼 색상", list(VestColor))],
        ),
    ]


def fire_classes() -> list[ClassSpecParam]:
    return [
        ClassSpecParam(name="fire", allowed_types=["bbox", "polygon"]),
        ClassSpecParam(name="smoke", allowed_types=["bbox", "polygon"]),
    ]


TARGETS = {
    "ppe": {
        "dataset_name": "lastsight-ppe",
        "project_name": "LastSight PPE (person/helmet/vest)",
        "classes": ppe_classes,
    },
    "fire": {
        "dataset_name": "lastsight-fire-smoke",
        "project_name": "LastSight Fire/Smoke",
        "classes": fire_classes,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=TARGETS.keys(), required=True)
    parser.add_argument("--step", choices=["dataset", "project"], required=True)
    parser.add_argument("--dataset-id", help="--step project 에서 필요. --step dataset에서 나온 id를 넣는다.")
    args = parser.parse_args()

    spec = TARGETS[args.target]
    client = get_client()

    if args.step == "dataset":
        dataset = client.datasets.create(name=spec["dataset_name"], description=f"LastSight AI — {args.target} 데이터셋")
        print(f"데이터셋 생성: {dataset.name} ({dataset.id})")
        print()
        print("다음 단계: 이미지를 업로드하세요 →")
        print(f"  python -m bdai_pipeline.upload_dataset --dataset-id {dataset.id} --source <이미지 폴더>")
        print("업로드가 끝난 뒤 프로젝트를 생성하세요 →")
        print(f"  python -m bdai_pipeline.create_project_schema --target {args.target} --step project --dataset-id {dataset.id}")
        return

    # step == "project"
    if not args.dataset_id:
        raise SystemExit("--step project 에는 --dataset-id 가 필요합니다 (이미지가 이미 업로드된 데이터셋).")

    asset_count = client.assets.list(args.dataset_id, limit=1, include_total=True).total
    if not asset_count:
        raise SystemExit(
            f"데이터셋 {args.dataset_id}에 에셋이 없습니다. "
            "upload_dataset.py로 이미지를 먼저 업로드한 뒤 다시 실행하세요."
        )
    print(f"데이터셋 {args.dataset_id}에 에셋 {asset_count}개 확인됨. 프로젝트 생성 진행.")

    project = client.projects.create(
        name=spec["project_name"],
        dataset_id=args.dataset_id,
        scope={"all": True},
        classes=spec["classes"](),
        dataset_kind="image",
    )
    print(f"프로젝트 생성: {project.name} ({project.id})")

    classes = client.classes.list(project.id)
    for c in classes.classes:
        print(f"  - 클래스 등록됨: {c.name} ({c.id}) types={c.allowed_types}")


if __name__ == "__main__":
    main()
