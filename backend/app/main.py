from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import annotate, briefing, health, incidents, ppe, scenario, workers, zone_maps
from app.ws import live

app = FastAPI(title="LastSight AI API")

# 개발 단계 대시보드(Vite dev server, 기본 5173 포트)에서 자유롭게 호출할 수 있도록 허용.
# 배포 전에는 실제 프론트엔드 도메인으로 좁혀야 함.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(workers.router)
app.include_router(briefing.router)
app.include_router(zone_maps.router)
app.include_router(ppe.router)
app.include_router(scenario.router)
app.include_router(live.router)
app.include_router(annotate.router)
app.include_router(incidents.router)

_DEMO_FRAMES_DIR = Path(__file__).resolve().parents[1] / "data" / "demo" / "frames"
if _DEMO_FRAMES_DIR.exists():
    app.mount("/demo-frames/frames", StaticFiles(directory=_DEMO_FRAMES_DIR), name="demo-frames")

_ANNOTATE_JOBS_DIR = Path(__file__).resolve().parents[1] / "data" / "annotate_jobs"
_ANNOTATE_JOBS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/annotate-frames", StaticFiles(directory=_ANNOTATE_JOBS_DIR), name="annotate-frames")

_TOOLS_DIR = Path(__file__).resolve().parent / "static"


@app.get("/tools/annotate")
def annotate_tool_page():
    return FileResponse(_TOOLS_DIR / "annotate.html")
