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

- `app/api/` — HTTP 라우터. 데모 시나리오 재생 상태(`app/pipeline/scenario_runner.py`)와 `app/rules/*` 로그 모듈을 그대로 조회·조합해서 응답한다(더미 데이터 아님). `situation_chat.py`가 영상 옆 구조 브리핑 챗봇용 Gemini 대화 엔드포인트(`POST /situation-chat`)
- `app/inference/` — 탐지 모델(person/helmet/vest, fire/smoke) 추론 래퍼(`detector.py`), ZERO 2차 확인(`situation_probe.py`), Gemini 상황 요약(`briefing.py`, BDAI 게이트웨이 재사용)
- `app/rules/` — 구역 판정(`zone.py`), 화재경보 자동 트리거(`alarm_trigger.py`)+로그(`fire_alert_log.py`), PPE 착용 판정(`ppe_compliance.py`)+감지 on/off 설정(`ppe_settings.py`)+미착용 로그·검토·병합(`ppe_violation_log.py`), 구역별 상황 집계 로그(`zone_situation_log.py`)
- `app/pipeline/scenario_runner.py` — 데모 시나리오 재생 오케스트레이터. 매 프레임 위 규칙 모듈들을 실제로 호출해 in-memory 상태(`STATE`)를 갱신하고 REST/웹소켓에 공유. 화재 발생 전에는 추적 없이 프레임마다 PPE 판정만, 화재 발생 후에는 매초 `situation_probe`로 2차 확인 카드를 쌓는 방식이다(개인별 추적 상태는 화면에 안 씀 — `docs/development_log.md` 51번 참고)
- `app/tracking/byte_track.py`, `app/rules/state_engine.py`, `app/rules/worker_log.py` — 예전 개인별 추적 기반 설계에서 쓰던 모듈. 지금 실시간 파이프라인에서는 더 안 쓰지만, 각자 단위 테스트가 딸려 있어 그대로 남겨뒀다(vestigial)
- `app/ws/live.py` — 실시간 상태 브로드캐스트 웹소켓
- `app/briefing/` — 참조 프레임 선택, (예전 개인별) 구조카드 생성
- `app/models/schemas.py` — 클래스·속성·이벤트 라벨 정의 (CLAUDE.md 4번과 동기화 유지)

## 테스트

```bash
pytest tests/
```
