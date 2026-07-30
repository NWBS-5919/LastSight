"""카메라별 구역 판정.

카메라 화면 좌표 → 공장 평면도 구역(A/B/C 등) 매핑. 좌표는
data/zone_maps/ 의 카메라별 json 파일에 정의하고(관리자 UI 또는 직접 편집),
여기서는 그 정의를 읽어 판정만 한다.
"""

import json
from pathlib import Path

from app.models.schemas import ZoneMapConfig

ZONE_MAP_DIR = Path(__file__).resolve().parents[3] / "data" / "zone_maps"


def zone_map_path(camera_id: str) -> Path:
    return ZONE_MAP_DIR / f"{camera_id}.json"


def load_zone_map(camera_id: str) -> ZoneMapConfig:
    path = zone_map_path(camera_id)
    if not path.exists():
        return ZoneMapConfig(camera_id=camera_id)
    return ZoneMapConfig.model_validate_json(path.read_text(encoding="utf-8"))


def save_zone_map(config: ZoneMapConfig) -> None:
    ZONE_MAP_DIR.mkdir(parents=True, exist_ok=True)
    path = zone_map_path(config.camera_id)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """레이캐스팅(ray casting) 알고리즘. 외부 라이브러리 없이 순수 파이썬으로 구현."""
    x, y = point
    inside = False
    n = len(polygon)
    x1, y1 = polygon[-1]
    for x2, y2 in polygon:
        if (y1 > y) != (y2 > y):
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def which_zone(camera_id: str, point_xy: tuple[float, float]) -> str | None:
    """주어진 좌표가 어느 구역 폴리곤 안에 있는지 판정. 여러 구역과 겹치면 먼저 정의된 구역 우선."""
    config = load_zone_map(camera_id)
    for zone in config.zones:
        if _point_in_polygon(point_xy, zone.polygon):
            return zone.zone_id
    return None
