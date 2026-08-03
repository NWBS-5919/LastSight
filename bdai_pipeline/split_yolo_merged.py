"""data/yolo_merged를 train/val로 분할하고 Ultralytics용 data.yaml을 만든다.
이미지 파일은 옮기지 않고(심볼릭 링크라 이미 가볍다) train.txt/val.txt에 경로만 나눠 담는다.
BDAI 학습 카탈로그 기본값(train 0.8 / val 0.1 / test 0.1)과 맞추되, 로컬 데모용이라 test는 생략하고 val 10%.
"""

from __future__ import annotations

import random
from pathlib import Path

from bdai_pipeline.build_yolo_merged import CLASSES

SEED = 42
VAL_RATIO = 0.1


def main() -> None:
    root = Path("data/yolo_merged")
    images_dir = root / "images"
    labels_dir = root / "labels"

    all_images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    # 라벨 없는(빈) 이미지는 애초에 build_yolo_merged에서 안 만들어지지만, 혹시 몰라 한 번 더 확인
    all_images = [p for p in all_images if (labels_dir / f"{p.stem}.txt").exists()]

    rng = random.Random(SEED)
    rng.shuffle(all_images)

    n_val = int(len(all_images) * VAL_RATIO)
    val_images = all_images[:n_val]
    train_images = all_images[n_val:]

    # 주의: .resolve()를 쓰면 심볼릭 링크가 원본 소스 경로로 풀려버려서, Ultralytics가
    # "images"->"labels" 문자열 치환으로 라벨을 찾을 때 우리가 만든 data/yolo_merged/labels/가
    # 아니라 원본 소스 쪽의(존재하지 않거나, SFCHD처럼 클래스 체계가 다른 옛) 라벨을 잘못 읽는다.
    # .absolute()는 심볼릭 링크를 풀지 않고 경로만 절대경로로 만들어 이 문제를 피한다.
    (root / "train.txt").write_text("\n".join(str(p.absolute()) for p in train_images), encoding="utf-8")
    (root / "val.txt").write_text("\n".join(str(p.absolute()) for p in val_images), encoding="utf-8")

    yaml_content = f"""# LastSight PPE 로컬 YOLO 학습용 (BDAI 스냅샷 정체 우회 경로)
path: {root.resolve()}
train: train.txt
val: val.txt

names:
{chr(10).join(f'  {i}: {name}' for i, name in enumerate(CLASSES))}
"""
    (root / "data.yaml").write_text(yaml_content, encoding="utf-8")

    print(f"train: {len(train_images)}장")
    print(f"val: {len(val_images)}장")
    print(f"data.yaml 작성 완료: {root / 'data.yaml'}")


if __name__ == "__main__":
    main()
