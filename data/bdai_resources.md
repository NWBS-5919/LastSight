# BDAI에 실제로 생성된 리소스

`bdai_pipeline/create_project_schema.py`로 만든 실제 데이터셋/프로젝트 ID 기록. 스크립트 재실행 시 중복 생성 방지용으로 참고.

## 데이터셋

| 이름 | dataset_id | 용도 |
|---|---|---|
| lastsight-ppe | `7eac627c-2782-4ef8-a3a3-de625a80d487` | person/helmet/vest (자체 촬영 + 공개데이터) |
| lastsight-fire-smoke | `6fa98c86-34f1-48f9-85e5-89ad190a0d72` | fire/smoke (공개데이터 전용) |

## 프로젝트

| 이름 | project_id | 클래스 | 어노테이션 수 |
|---|---|---|---|
| SAIV PPE (person/helmet/vest) | `ddc1dbe2-104c-4c4b-8741-68c5563733c7` | person(6,600) · helmet(5,164) · vest(5,209) | 16,973 |
| SAIV Fire/Smoke | `abad271f-68e8-4f63-a37a-f53e04b532d6` | fire(10,318) · smoke(13,328) | 23,646 |

## 사용한 소스 데이터

| 소스 | 이미지 수 | 형식 | 프로젝트 |
|---|---|---|---|
| Construction Site Safety (Roboflow, CC BY 4.0) | 717 | COCO | PPE |
| SFCHD | 4,000 (12,372장 중 샘플) | YOLO | PPE |
| Fire and Smoke Segmentation (Roboflow, CC BY 4.0) | 201 (증강 제거) | COCO Segmentation | Fire/Smoke |
| AI Hub 176 "화재 발생 예측 데이터" 화재씬 (공공데이터, 출처 표기 조건) | 13,159 | bbox+polygon 커스텀(`aihub176`) | Fire/Smoke |

## 스냅샷

| 프로젝트 | version_id | 이름 | 에셋 | 클래스(+속성) |
|---|---|---|---|---|
| PPE | `2b89f582-6d31-45a5-acde-aa027ac5eb94` | v1-imported | 4,480 | 7 (person/helmet/vest + 속성 4개) |
| Fire/Smoke | `91c555af-363c-4543-a275-6742fb26ce29` | v1-imported (구버전, 195장 시절) | 195 | 2 (fire/smoke) |
| Fire/Smoke | `3ff88094-de46-4472-9668-f2038a073059` | v2-imported (AI Hub 176 반영) | 13,354 | 2 (fire/smoke) |

라벨 없는 에셋(PPE 200개)은 스냅샷에서 자동 제외됨(`--filter annotated=true`).

## AI Hub 176 반입 시 겪은 이슈 (재현 방지용 메모)

- **프로젝트 스코프 고정 문제**: 프로젝트를 처음 만들 때 스코프가 그 시점의 에셋 목록(195장)으로 고정되고, 이후 데이터셋에 새로 업로드한 에셋은 자동으로 프로젝트에 편입되지 않는다(`annotations.bulk_create`가 "filename not found in this project's dataset"로 실패). 새 이미지를 업로드한 뒤에는 반드시 `client.project_assets.bulk_add(project_id, filter={})`로 프로젝트 스코프를 갱신해야 한다.
- **폴리곤 payload 초과**: 원본 라벨의 폴리곤이 평균 1,000개, 최대 4,000개에 달하는 점을 담고 있어(크라우드 워커가 픽셀 단위로 촘촘히 클릭 + 완전 중복점 다수) 1,000개씩 묶은 배치가 413(Request Entity Too Large)로 실패했다. `cv2.approxPolyDP`(Douglas-Peucker)로 단순화해 평균 53개 점으로 줄였고, `bdai_pipeline/import_public_dataset.py`의 배치도 개수 대신 직렬화 바이트 크기 기준(2MB) 동적 배치로 바꿨다.
- **결손 좌표점**: 극소수 폴리곤에 `[96]`처럼 `[x, y]` 쌍이 아닌 점이 섞여 있어(원본 라벨링 데이터 자체의 결함으로 추정) numpy 변환이 실패했다. 파싱 단계에서 `len(pt) == 2`가 아닌 점을 걸러내도록 수정.

## 다음 단계

- [ ] BDAI 웹에서 라벨 몇 개 샘플 검수 (클래스 매핑이 실제로 맞게 들어갔는지 눈으로 확인)
- [ ] 자체 촬영 영상 업로드 후 같은 프로젝트에 합치기 (또는 검수 후 별도 관리, 새 스냅샷으로)
- [x] Fire/Smoke 새 스냅샷 생성 (v2-imported, 13,354 에셋)
- [ ] Fire/Smoke 재학습 (`bdai_pipeline/training_run.py`)
