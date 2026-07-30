#!/usr/bin/env bash
set -euo pipefail

source /opt/homebrew/anaconda3/etc/profile.d/conda.sh
conda activate lastsight

cd "$(dirname "$0")/.."

PPE_DATASET_ID="7eac627c-2782-4ef8-a3a3-de625a80d487"
FIRE_DATASET_ID="6fa98c86-34f1-48f9-85e5-89ad190a0d72"

CSS="data/public_datasets/construction-site-safety"
SFCHD="data/public_datasets/sfchd"
FIRE="data/public_datasets/fire-and-smoke-segmentation"

CSS_MAP='{"Person":"person","Hardhat":"helmet","Safety Vest":"vest"}'
SFCHD_MAP='{"person":"person","helmet":"helmet","safety_clothes":"vest"}'
FIRE_MAP='{"fire":"fire","smoke":"smoke"}'

echo "=== [1/3] 이미지 업로드 ==="

echo "--- Construction Site Safety (train/valid/test) ---"
for split in train valid test; do
  python -m bdai_pipeline.import_public_dataset upload --format coco --source "$CSS/$split" --dataset-id "$PPE_DATASET_ID"
done

echo "--- SFCHD (4000장 샘플) ---"
python -m bdai_pipeline.import_public_dataset upload --format yolo --source "$SFCHD" --dataset-id "$PPE_DATASET_ID" --max-images 4000

echo "--- Fire and Smoke Segmentation (증강 제거) ---"
python -m bdai_pipeline.import_public_dataset upload --format coco-seg --source "$FIRE/train" --dataset-id "$FIRE_DATASET_ID" --dedupe-suffix ".rf."
python -m bdai_pipeline.import_public_dataset upload --format coco-seg --source "$FIRE/valid" --dataset-id "$FIRE_DATASET_ID"
python -m bdai_pipeline.import_public_dataset upload --format coco-seg --source "$FIRE/test" --dataset-id "$FIRE_DATASET_ID"

echo "=== [2/3] 프로젝트 + 스키마 생성 ==="
PPE_OUT=$(python -m bdai_pipeline.create_project_schema --target ppe --step project --dataset-id "$PPE_DATASET_ID")
echo "$PPE_OUT"
PPE_PROJECT_ID=$(echo "$PPE_OUT" | grep '프로젝트 생성: ' | sed -E 's/.*\(([^)]+)\).*/\1/')

FIRE_OUT=$(python -m bdai_pipeline.create_project_schema --target fire --step project --dataset-id "$FIRE_DATASET_ID")
echo "$FIRE_OUT"
FIRE_PROJECT_ID=$(echo "$FIRE_OUT" | grep '프로젝트 생성: ' | sed -E 's/.*\(([^)]+)\).*/\1/')

echo "PPE_PROJECT_ID=$PPE_PROJECT_ID"
echo "FIRE_PROJECT_ID=$FIRE_PROJECT_ID"

echo "=== [3/3] 라벨 반입 ==="

echo "--- Construction Site Safety ---"
for split in train valid test; do
  python -m bdai_pipeline.import_public_dataset annotate --format coco --source "$CSS/$split" --project-id "$PPE_PROJECT_ID" --class-map "$CSS_MAP"
done

echo "--- SFCHD ---"
python -m bdai_pipeline.import_public_dataset annotate --format yolo --source "$SFCHD" --project-id "$PPE_PROJECT_ID" --class-map "$SFCHD_MAP" --max-images 4000

echo "--- Fire and Smoke Segmentation ---"
python -m bdai_pipeline.import_public_dataset annotate --format coco-seg --source "$FIRE/train" --project-id "$FIRE_PROJECT_ID" --class-map "$FIRE_MAP" --dedupe-suffix ".rf."
python -m bdai_pipeline.import_public_dataset annotate --format coco-seg --source "$FIRE/valid" --project-id "$FIRE_PROJECT_ID" --class-map "$FIRE_MAP"
python -m bdai_pipeline.import_public_dataset annotate --format coco-seg --source "$FIRE/test" --project-id "$FIRE_PROJECT_ID" --class-map "$FIRE_MAP"

echo "=== 완료 ==="
echo "PPE_PROJECT_ID=$PPE_PROJECT_ID"
echo "FIRE_PROJECT_ID=$FIRE_PROJECT_ID"
