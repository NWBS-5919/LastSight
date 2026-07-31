"""PPE(안전모·조끼) 미착용 감지 이력 저장·조회 (app/rules/worker_log.py와 같은 파일 기반 패턴).

착용 → 미착용으로 바뀐 순간에만 한 줄 남긴다(계속 미착용 상태가 지속되는 동안 매 프레임
기록하지 않음). 추적 ID의 연속성을 신뢰하지 않는다는 전제로 설계했다(development_log.md
참고 — CCTV 환경에서 사람이 사라졌다 나타나면 새 ID가 부여되는 걸 막을 수 없다). 그래서
같은 사람이 ID가 바뀌어도 그냥 새 위반 건으로 다시 기록될 뿐이며, 관리자가 각 로그에 붙은
증거 사진(frame_path/bbox_xyxy)을 직접 보고 "같은 사람인지"를 판단하도록 한다 — AI가
ID를 억지로 이어붙이려 하지 않는다.
"""

import json
from pathlib import Path

from app.models.schemas import PpeViolationLogEntry

LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "ppe_violation_logs"


def _log_path(camera_id: str, track_id: str) -> Path:
    return LOG_DIR / camera_id / f"{track_id}.json"


def load_ppe_violation_log(camera_id: str, track_id: str) -> list[PpeViolationLogEntry]:
    path = _log_path(camera_id, track_id)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [PpeViolationLogEntry.model_validate(v) for v in raw]


def _append(camera_id: str, entry: PpeViolationLogEntry) -> None:
    path = _log_path(camera_id, entry.track_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    log = load_ppe_violation_log(camera_id, entry.track_id)
    log.append(entry)
    path.write_text(json.dumps([e.model_dump() for e in log], ensure_ascii=False, indent=2), encoding="utf-8")


def record_if_newly_violated(
    camera_id: str,
    track_id: str,
    *,
    violation: str,
    was_violated_before: bool,
    zone: str | None,
    now_iso: str,
    frame_path: str | None,
    bbox_xyxy: tuple[float, float, float, float] | None,
    confidence: float | None,
) -> None:
    """직전 프레임엔 미착용이 아니었는데 이번에 새로 미착용이 됐을 때만 기록한다."""
    if was_violated_before:
        return
    _append(
        camera_id,
        PpeViolationLogEntry(
            track_id=track_id,
            violation=violation,
            zone=zone,
            at=now_iso,
            frame_path=frame_path,
            bbox_xyxy=bbox_xyxy,
            confidence=confidence,
        ),
    )
