"""화재 발생 후 구역별 상황 집계 이력 저장·조회 (app/rules/fire_alert_log.py와 같은
카메라당 파일 하나 append-only 패턴).

장기체류(PROLONGED_PRESENCE) 전환이 하나라도 생길 때마다 app.inference.situation_probe의
probe_zone_situation 결과를 ZoneSituationLogEntry로 여기 남긴다. 화재 이벤트 자체가
카메라별로 하나뿐인 시나리오라 track_id 분기가 필요 없다(fire_alert_log.py와 동일한
이유로 단순 append-only 리스트면 충분).
"""

import json
from pathlib import Path

from app.models.schemas import ZoneSituationLogEntry

LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "zone_situation_logs"


def _log_path(camera_id: str) -> Path:
    return LOG_DIR / f"{camera_id}.json"


def load_zone_situation_log(camera_id: str) -> list[ZoneSituationLogEntry]:
    path = _log_path(camera_id)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ZoneSituationLogEntry.model_validate(v) for v in raw]


def append_zone_situation(entry: ZoneSituationLogEntry) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = load_zone_situation_log(entry.camera_id)
    log.append(entry)
    _log_path(entry.camera_id).write_text(
        json.dumps([e.model_dump() for e in log], ensure_ascii=False, indent=2), encoding="utf-8"
    )
