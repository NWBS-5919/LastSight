"""카메라별 PPE(헬멧/조끼) 감지 on/off 설정 저장·조회 (app/rules/zone.py와 같은 파일 기반 패턴).

관리자가 "이 현장은 조끼 규정이 없다" 같은 이유로 특정 장비 감지를 끌 수 있게 한다.
꺼진 항목은 app/rules/ppe_compliance.py에서 판정 자체를 안 한다(UNKNOWN 취급) — 오탐/불필요한
경고를 줄이기 위함이지, 착용했는데 미착용으로 잘못 판단하는 것과는 다른 문제다.
"""

from pathlib import Path

from app.models.schemas import PpeDetectionSettings

SETTINGS_DIR = Path(__file__).resolve().parents[3] / "data" / "ppe_settings"


def _settings_path(camera_id: str) -> Path:
    return SETTINGS_DIR / f"{camera_id}.json"


def load_ppe_settings(camera_id: str) -> PpeDetectionSettings:
    path = _settings_path(camera_id)
    if not path.exists():
        return PpeDetectionSettings(camera_id=camera_id)
    return PpeDetectionSettings.model_validate_json(path.read_text(encoding="utf-8"))


def save_ppe_settings(settings: PpeDetectionSettings) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _settings_path(settings.camera_id)
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
