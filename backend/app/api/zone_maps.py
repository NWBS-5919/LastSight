"""카메라별 구역/출구선 설정 조회·저장 + 참조 이미지 업로드.

관리자가 프론트엔드 에디터에서 화면에 클릭해 구역·출구선을 그리면 이 API로 저장한다.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.models.schemas import ZoneMapConfig
from app.rules.zone import load_zone_map, save_zone_map, zone_map_path

router = APIRouter(prefix="/zone-maps", tags=["zone-maps"])

IMAGE_DIR = Path(__file__).resolve().parents[3] / "data" / "zone_maps" / "images"


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
