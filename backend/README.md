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

- `app/api/` — HTTP 라우터. 데모 시나리오 재생 상태(`app/pipeline/scenario_runner.py`)와 `app/rules/*` 로그 모듈을 그대로 조회·조합해서 응답한다(더미 데이터 아님)
- `app/inference/` — 탐지 모델(person/helmet/vest, fire/smoke) 추론 래퍼 + ZERO 2차 확인(`situation_probe.py`)
- `app/tracking/` — ByteTrack 계열 다중 객체 추적(`byte_track.py`). 화재경보 발생 시점부터만 사용
- `app/rules/` — 구역 판정(`zone.py`), 관리구역(소화기/전기패널/비상구) 변화 감지(`clearance_zone.py`)+로그(`clearance_zone_log.py`), 화재경보 자동 트리거(`alarm_trigger.py`)+로그(`fire_alert_log.py`), PPE 착용 판정(`ppe_compliance.py`)+감지 on/off 설정(`ppe_settings.py`)+미착용 로그(`ppe_violation_log.py`), 최종 상태 결정(`state_engine.py`)+작업자 이벤트 로그(`worker_log.py`), 구역별 상황 집계 로그(`zone_situation_log.py`), 확인 우선순위 트리아지(`triage.py`)
- `app/pipeline/scenario_runner.py` — 데모 시나리오 재생 오케스트레이터. 매 프레임 위 규칙 모듈들을 실제로 호출해 in-memory 상태(`STATE`)를 갱신하고 REST/웹소켓에 공유
- `app/ws/live.py` — 실시간 상태 브로드캐스트 웹소켓
- `app/briefing/` — 참조 프레임 선택, 구조카드 생성
- `app/models/schemas.py` — 클래스·속성·이벤트 라벨 정의 (CLAUDE.md 4번과 동기화 유지)

## 테스트

```bash
pytest tests/
```
