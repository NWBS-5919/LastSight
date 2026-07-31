"""데모 시나리오 재생 제어 API.

발표자가 브라우저에서 "시나리오 시작" 버튼을 누르면 이 API가 백그라운드로
`scenario_runner.run_scenario()`를 실행한다. 실제 카메라 입력이 없는 데모 환경에서
정상→연기감지→경보→상태전환→구조카드 흐름을 재현하기 위한 용도.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.pipeline import scenario_runner

router = APIRouter(prefix="/scenario", tags=["scenario"])

_task: asyncio.Task | None = None


@router.post("/start")
async def start_scenario(speed: float = 1.0) -> dict:
    global _task
    if _task is not None and not _task.done():
        return {"status": "already_running"}
    _task = asyncio.create_task(scenario_runner.run_scenario(speed=speed))
    return {"status": "started", "speed": speed}


@router.post("/reset")
async def reset_scenario() -> dict:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    scenario_runner.reset()
    await scenario_runner._broadcast()
    return {"status": "reset"}


@router.get("/state")
async def get_state() -> dict:
    return scenario_runner.snapshot_dict()
