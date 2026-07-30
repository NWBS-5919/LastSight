from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import briefing, health, workers, zone_maps

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
