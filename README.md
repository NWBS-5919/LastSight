# LastSight AI

SuperB AI × BDAI 해커톤 — 산업안전·물류 트랙. 자세한 배경·규칙은 `CLAUDE.md`와 `docs/`를 참고.

## 폴더 구조

```
.
├── CLAUDE.md                 # 프로젝트 지침 (Claude Code가 자동으로 읽는 파일)
├── docs/                      # 기획서·해커톤 규정·BDAI 매뉴얼 정리본
├── backend/                   # FastAPI 서버 (탐지·추적·규칙엔진 결과 서빙)
├── frontend/                  # React+Vite 대시보드 (실시간 웹소켓 연동, 데모 시나리오 재생 화면)
├── bdai_pipeline/              # BDAI SDK 연동 스크립트 (업로드·스키마·익스포트·학습·자동라벨링)
├── data/
│   ├── raw/                   # 촬영 원본 영상 (git 추적 제외)
│   ├── frames/                # 샘플링 이미지 (git 추적 제외)
│   ├── exports/                # BDAI 스냅샷 익스포트 (git 추적 제외)
│   ├── zone_maps/              # 카메라별 구역·관리구역(소화기/전기패널/비상구) 폴리곤 정의 및 기준사진(json)
│   ├── fire_alerts/            # 카메라별 화재경보 발생 로그 (json)
│   ├── worker_logs/            # 작업자별 상태 변화 이벤트 로그 (json, 화재경보 이후에만 생성)
│   ├── clearance_zone_logs/    # 관리구역 상태 변화 로그 (json)
│   ├── ppe_settings/           # 카메라별 헬멧/조끼 감지 on/off 설정 (json)
│   ├── ppe_violation_logs/     # 평상시 PPE 미착용 이벤트 로그 — 카메라당 파일 하나 (json)
│   └── zone_situation_logs/    # 화재 후 구역별 상황 집계 로그 — 카메라당 파일 하나 (json)
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

```bash
# 3. 프론트엔드 (백엔드가 8000번에서 떠 있어야 함)
cd frontend && npm install && npm run dev
```

프론트엔드는 `http://localhost:5173`에서 뜨고, 웹소켓으로 백엔드(`app/ws/live.py`)와 실시간 연동해 데모 시나리오(정상 → 화재감지 → 경보 → 상태전환 → 구조카드)를 재생한다. 화면 구성·표시 데이터 상세는 `docs/screen_guide.md` 참고.

## 역할 분담

- **A (데이터/라벨링)**: `bdai_pipeline/`, `data/`, BDAI 웹 화면에서 라벨링·검수·스냅샷·학습
- **B (모델/서비스)**: `backend/`, `frontend/`

자세한 파이프라인 단계와 절대 원칙(안전·개인정보)은 `CLAUDE.md`를 반드시 확인.
