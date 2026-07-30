"""화재경보 이력 저장·조회 (app/rules/zone.py와 같은 파일 기반 영속화 패턴).

대시보드 이벤트 피드에 "10:32:15 Room2에서 화재 감지"처럼 표시할 때 이 로그를 사용한다.
"""

import json
from pathlib import Path

from app.models.schemas import FireAlert

LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "fire_alerts"


def _log_path(camera_id: str) -> Path:
    return LOG_DIR / f"{camera_id}.json"


def load_fire_alerts(camera_id: str) -> list[FireAlert]:
    path = _log_path(camera_id)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [FireAlert.model_validate(v) for v in raw]


def append_fire_alert(alert: FireAlert) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    alerts = load_fire_alerts(alert.camera_id)
    alerts.append(alert)
    path = _log_path(alert.camera_id)
    path.write_text(json.dumps([a.model_dump() for a in alerts], ensure_ascii=False, indent=2), encoding="utf-8")


def latest_fire_alert(camera_id: str) -> FireAlert | None:
    alerts = load_fire_alerts(camera_id)
    return max(alerts, key=lambda a: a.triggered_at) if alerts else None
