from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import annotate, briefing, health, incidents, ppe, scenario, situation_chat, workers, zone_maps
from app.ws import live

app = FastAPI(title="LastSight AI API")

# 개발 단계 대시보드(Vite dev server, 기본 5173 포트)에서 자유롭게 호출할 수 있도록 허용.
# 배포 전에는 실제 프론트엔드 도메인으로 좁혀야 함.
app.add_middleware(
    CORSMiddleware,
    # localhost와 127.0.0.1은 브라우저에서 서로 다른 origin이다. Vite가 어느 주소로
    # 열렸든 PPE 검토(PATCH)·병합(POST)의 preflight가 통과하도록 둘 다 허용한다.
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
app.include_router(situation_chat.router)

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


# 배포(Render 등)에서는 프론트엔드 빌드 결과물을 이 백엔드가 그대로 서빙해 서비스
# 하나로 끝낸다(Dockerfile이 frontend/dist를 여기 복사해둠) — CORS·별도 정적 호스팅이
# 필요 없다. 로컬 개발(vite dev server, 5173 포트)에서는 이 디렉터리가 없으므로 그냥
# 건너뛴다. 반드시 다른 라우터/마운트를 다 등록한 "뒤"에 "/"로 잡아야 API 경로를 가리지
# 않는다.
_FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST_DIR, html=True), name="frontend")
