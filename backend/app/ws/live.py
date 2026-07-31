"""실시간 대시보드 푸시용 웹소켓.

`app.pipeline.scenario_runner`가 프레임마다 만드는 상태 스냅샷을 연결된 모든 클라이언트에
그대로 방송한다. 연결 직후에는 현재 스냅샷을 즉시 한 번 보내 새로고침 후에도 바로
화면이 채워지게 한다.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.pipeline import scenario_runner

router = APIRouter(tags=["ws"])

_connections: set[WebSocket] = set()


async def _broadcast(snapshot: dict) -> None:
    dead: list[WebSocket] = []
    for ws in _connections:
        try:
            await ws.send_json(snapshot)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)


@router.websocket("/ws/live")
async def live_updates(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    if _broadcast not in scenario_runner._listeners:
        scenario_runner.add_listener(_broadcast)
    try:
        await websocket.send_json(scenario_runner.snapshot_dict())
        while True:
            # 클라이언트는 별도 메시지를 보낼 필요 없음 — 연결 유지 목적으로만 수신 대기
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
