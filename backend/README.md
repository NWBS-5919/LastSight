# backend

FastAPI 서버. 추론·추적·규칙엔진 결과를 API/WebSocket으로 프론트엔드에 제공.

## 실행

```bash
conda env create -f ../environment.yml   # 최초 1회
conda activate lastsight
cd backend
uvicorn app.main:app --reload --port 8000
```

`.env.example`을 프로젝트 루트에 `.env`로 복사하고 값을 채워야 `bdai_pipeline/`과 BDAI 연동이 동작한다.

## 폴더 역할

- `app/api/` — HTTP 라우터. 지금은 더미 데이터를 반환하며, 실제 로직은 아래 모듈들과 연결 예정
- `app/inference/` — 탐지 모델(person/helmet/vest) 추론 래퍼
- `app/tracking/` — ByteTrack 등 다중 객체 추적
- `app/rules/` — 구역 판정(`zone.py`), 관리구역(소화기/전기패널/비상구) 변화 감지(`clearance_zone.py`), 최종 상태 결정(`state_engine.py`), 화재경보 로그(`fire_alert_log.py`), 작업자 이벤트 로그(`worker_log.py`)
- `app/briefing/` — 참조 프레임 선택, 구조카드 생성
- `app/models/schemas.py` — 클래스·속성·이벤트 라벨 정의 (CLAUDE.md 4번과 동기화 유지)

## 테스트

```bash
pytest tests/
```
