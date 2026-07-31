"""카메라별 구역/출구선 설정 조회·저장 + 참조 이미지 업로드.

관리자가 프론트엔드 에디터에서 화면에 클릭해 구역·출구선을 그리면 이 API로 저장한다.
관리 구역(clearance zone — 소화기/전기패널/비상구 상시 점검) 관련 엔드포인트도 여기 같이 둔다.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.inference.situation_probe import CLEARANCE_ZONE_PROMPTS, probe_situation
from app.models.schemas import ClearanceZoneState, ClearanceZoneStatus, ZoneMapConfig
from app.rules.clearance_zone import (
    baseline_image_path,
    evaluate_clearance_zone,
    load_clearance_statuses,
    save_clearance_status,
)
from app.rules.clearance_zone_log import record_if_changed as record_clearance_zone_log
from app.rules.zone import load_zone_map, save_zone_map, zone_map_path

router = APIRouter(prefix="/zone-maps", tags=["zone-maps"])

IMAGE_DIR = Path(__file__).resolve().parents[3] / "data" / "zone_maps" / "images"


def _decode_image(raw: bytes) -> np.ndarray:
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="이미지 디코딩 실패 (지원 형식: jpg/png)")
    return frame


def _get_clearance_zone_or_404(camera_id: str, zone_id: str):
    config = load_zone_map(camera_id)
    for zone in config.clearance_zones:
        if zone.zone_id == zone_id:
            return config, zone
    raise HTTPException(status_code=404, detail=f"관리 구역을 찾을 수 없음: {zone_id}")


@router.get("/{camera_id}", response_model=ZoneMapConfig)
def get_zone_map(camera_id: str) -> ZoneMapConfig:
    return load_zone_map(camera_id)


@router.put("/{camera_id}", response_model=ZoneMapConfig)
def put_zone_map(camera_id: str, config: ZoneMapConfig) -> ZoneMapConfig:
    if config.camera_id != camera_id:
        raise HTTPException(status_code=400, detail="camera_id가 URL과 본문에서 다릅니다.")
    save_zone_map(config)
    return config


@router.post("/{camera_id}/reference-image")
async def upload_reference_image(camera_id: str, file: UploadFile) -> dict[str, str]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    dest = IMAGE_DIR / f"{camera_id}{ext}"
    dest.write_bytes(await file.read())
    return {"reference_image_url": f"/zone-maps/{camera_id}/reference-image"}


@router.get("/{camera_id}/reference-image")
def get_reference_image(camera_id: str):
    from fastapi.responses import FileResponse

    for ext in (".jpg", ".jpeg", ".png"):
        path = IMAGE_DIR / f"{camera_id}{ext}"
        if path.exists():
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="참조 이미지가 아직 업로드되지 않았습니다.")


@router.delete("/{camera_id}")
def delete_zone_map(camera_id: str) -> dict[str, bool]:
    path = zone_map_path(camera_id)
    if path.exists():
        path.unlink()
    return {"deleted": True}


# ---- 관리 구역(소화기/전기패널/비상구 상시 점검) ----


@router.get("/{camera_id}/clearance-zones/status", response_model=dict[str, ClearanceZoneStatus])
def get_clearance_statuses(camera_id: str) -> dict[str, ClearanceZoneStatus]:
    """등록된 관리 구역들의 현재 상태(정상/관찰중/이상확정/카메라장애) 전체를 반환."""
    return load_clearance_statuses(camera_id)


@router.post("/{camera_id}/clearance-zones/{zone_id}/baseline")
async def set_clearance_baseline(camera_id: str, zone_id: str, file: UploadFile) -> ClearanceZoneStatus:
    """"지금 상태를 기준으로 저장" — 관리 구역 등록 시 최초 1회, 또는 정당한 배치 변경 후 재설정."""
    config, zone = _get_clearance_zone_or_404(camera_id, zone_id)
    raw = await file.read()
    _decode_image(raw)  # 유효한 이미지인지만 검증

    dest = baseline_image_path(camera_id, zone_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)

    for z in config.clearance_zones:
        if z.zone_id == zone_id:
            z.baseline_frame_path = str(dest)
    save_zone_map(config)

    status = ClearanceZoneStatus(
        zone_id=zone_id, state=ClearanceZoneState.NORMAL, last_checked_at=datetime.now(UTC).isoformat()
    )
    save_clearance_status(camera_id, status)
    return status


@router.post("/{camera_id}/clearance-zones/{zone_id}/evaluate")
async def evaluate_clearance(
    camera_id: str,
    zone_id: str,
    file: UploadFile,
    person_boxes: str | None = Form(None, description='JSON 배열, 예: "[[x1,y1,x2,y2], ...]" (추적 파이프라인의 사람 박스)'),
) -> ClearanceZoneStatus:
    """현재 프레임 한 장을 평가해서 상태를 갱신한다. 실시간 추론 파이프라인이 프레임마다
    호출하거나, 파이프라인 연동 전 수동 검증용으로도 쓸 수 있다."""
    config, zone = _get_clearance_zone_or_404(camera_id, zone_id)
    if not zone.baseline_frame_path:
        raise HTTPException(status_code=400, detail="기준 화면이 아직 등록되지 않았습니다. baseline API를 먼저 호출하세요.")

    current_frame = _decode_image(await file.read())
    baseline_frame = cv2.imread(zone.baseline_frame_path)
    if baseline_frame is None:
        raise HTTPException(status_code=500, detail="저장된 기준 화면을 읽을 수 없습니다.")

    boxes = None
    if person_boxes:
        try:
            boxes = [tuple(b) for b in json.loads(person_boxes)]
        except (json.JSONDecodeError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"person_boxes 파싱 실패: {e}") from e

    now = datetime.now(UTC)
    prev = load_clearance_statuses(camera_id).get(zone_id)
    status = evaluate_clearance_zone(
        zone,
        prev_status=prev,
        now=now,
        current_frame=current_frame,
        baseline_frame=baseline_frame,
        person_boxes=boxes,
    )

    became_abnormal = status.state == ClearanceZoneState.ABNORMAL and (prev is None or prev.state != ClearanceZoneState.ABNORMAL)
    if became_abnormal:
        prompts = CLEARANCE_ZONE_PROMPTS.get(zone.zone_type.value, [])
        if prompts:
            status.situation_note = probe_situation(current_frame, prompts)

    record_clearance_zone_log(camera_id, prev, status, now.isoformat())
    save_clearance_status(camera_id, status)
    return status


@router.post("/{camera_id}/clearance-zones/{zone_id}/resolve")
async def resolve_clearance_zone(camera_id: str, zone_id: str, file: UploadFile | None = None) -> ClearanceZoneStatus:
    """관리자가 현장에서 조치를 마친 뒤 호출 — 상태를 정상으로 되돌린다.
    새 사진을 같이 올리면 그 사진을 새 기준 화면으로 재설정한다(레이아웃이 정당하게 바뀐 경우)."""
    config, zone = _get_clearance_zone_or_404(camera_id, zone_id)

    if file is not None:
        raw = await file.read()
        _decode_image(raw)
        dest = baseline_image_path(camera_id, zone_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        for z in config.clearance_zones:
            if z.zone_id == zone_id:
                z.baseline_frame_path = str(dest)
        save_zone_map(config)

    status = ClearanceZoneStatus(
        zone_id=zone_id, state=ClearanceZoneState.NORMAL, last_checked_at=datetime.now(UTC).isoformat()
    )
    save_clearance_status(camera_id, status)
    return status
