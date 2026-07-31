"""영상 업로드 → PPE(person/helmet/vest) 탐지 bbox 프레임으로 변환하는 독립 툴 API.

LastSight 대시보드와 무관하게, 모델 탐지 품질만 빠르게 확인하고 싶을 때 쓴다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.pipeline.video_annotate import annotate_video

router = APIRouter(prefix="/annotate", tags=["annotate"])


@router.post("/upload")
async def upload_and_annotate(file: UploadFile, sample_every: int = 4, max_frames: int = 80, confidence: float = 0.5) -> dict:
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        result = annotate_video(tmp_path, sample_every=sample_every, max_frames=max_frames, confidence=confidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        tmp_path.unlink(missing_ok=True)

    result["frame_urls"] = [f"/annotate-frames/{result['job_id']}/{f}" for f in result["frame_files"]]
    return result
