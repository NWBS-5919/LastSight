# LastSight AI

SuperB AI × BDAI 해커톤 — 산업안전·물류 트랙. 자세한 배경·규칙은 `CLAUDE.md`와 `docs/`를 참고.

## 폴더 구조

```
.
├── CLAUDE.md                 # 프로젝트 지침 (Claude Code가 자동으로 읽는 파일)
├── docs/                      # 기획서·해커톤 규정·BDAI 매뉴얼 정리본
├── backend/                   # FastAPI 서버 (탐지·추적·규칙엔진 결과 서빙)
├── bdai_pipeline/              # BDAI SDK 연동 스크립트 (업로드·스키마·익스포트·학습·자동라벨링)
├── data/
│   ├── raw/                   # 촬영 원본 영상 (git 추적 제외)
│   ├── frames/                # 샘플링 이미지 (git 추적 제외)
│   ├── exports/                # BDAI 스냅샷 익스포트 (git 추적 제외)
│   ├── zone_maps/              # 카메라별 구역·관리구역(소화기/전기패널/비상구) 폴리곤 정의 및 기준사진(json)
│   ├── fire_alerts/            # 카메라별 화재경보 발생 로그 (json)
│   └── worker_logs/            # 작업자별 상태 변화 이벤트 로그 (json)
├── experiments/logs/          # 실험 로그 (1~10차)
└── scripts/                   # 잡다한 유틸 스크립트
```

## 시작하기

```bash
# 1. 파이썬 환경
conda env create -f environment.yml
conda activate lastsight
cp .env.example .env   # SUPERB_AI_TENANT / SUPERB_AI_API_KEY 채우기

# 2. 백엔드
cd backend && uvicorn app.main:app --reload --port 8000
```

백엔드는 `http://localhost:8000`에서 뜨고, `http://localhost:8000/docs`에서 API 계약(Swagger UI)을 바로 확인할 수 있다.

> 프론트엔드(대시보드)는 이 저장소에 포함돼 있지 않다 — 프론트엔드 개발자가 위 API를 기준으로 새로 만든다. 화면 구성·표시 데이터는 `docs/screen_guide.md` 참고.

## 역할 분담

- **A (데이터/라벨링)**: `bdai_pipeline/`, `data/`, BDAI 웹 화면에서 라벨링·검수·스냅샷·학습
- **B (모델/서비스)**: `backend/`

자세한 파이프라인 단계와 절대 원칙(안전·개인정보)은 `CLAUDE.md`를 반드시 확인.
