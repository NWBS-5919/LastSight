from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_situation_chat_returns_reply(monkeypatch):
    import app.api.situation_chat as chat_module

    monkeypatch.setattr(chat_module, "answer_chat_message", lambda **kwargs: ("B구역에 2명 있습니다.", "/demo-frames/frames/0074.jpg"))

    res = client.post("/situation-chat", json=[{"role": "user", "content": "지금 상황 어때?"}])
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "B구역에 2명 있습니다."
    assert body["frame_path"] == "/demo-frames/frames/0074.jpg"
    assert "disclaimer" in body


def test_situation_chat_returns_502_when_generation_fails(monkeypatch):
    import app.api.situation_chat as chat_module

    monkeypatch.setattr(chat_module, "answer_chat_message", lambda **kwargs: None)

    res = client.post("/situation-chat", json=[{"role": "user", "content": "지금 상황 어때?"}])
    assert res.status_code == 502
