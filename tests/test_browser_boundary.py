from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from videoforge.server.boundary import BrowserBoundary


def client():
    app = FastAPI()
    app.add_middleware(
        BrowserBoundary, hosts=["localhost", "127.0.0.1", "::1", "video.example"], origins=["https://proxy.example"]
    )

    @app.post("/control")
    def control():
        return {"ok": True}

    @app.websocket("/events")
    async def events(ws: WebSocket):
        await ws.accept()
        await ws.send_json({"type": "hello"})

    return TestClient(app, base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize(
    "origin", ["https://foreign.example", "null", "http://127.0.0.1:9999", "http://127.0.0.1:8765/path"]
)
def test_foreign_origins_cannot_control_or_subscribe(origin):
    with client() as c:
        assert c.post("/control", headers={"Origin": origin}).status_code == 403
        with (
            pytest.raises(WebSocketDisconnect) as ex,
            c.websocket_connect("ws://127.0.0.1:8765/events", headers={"Origin": origin}),
        ):
            pass
        assert ex.value.code == 1008


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "http://127.0.0.1:8765"},
        {"Origin": "https://proxy.example"},
        {"Host": "localhost:5173", "Origin": "http://localhost:5173"},
        {"Host": "[::1]:8765", "Origin": "http://[::1]:8765"},
        {"Host": "video.example", "Origin": "http://video.example"},
    ],
)
def test_local_cli_desktop_dev_and_configured_proxy_access(headers):
    with client() as c:
        assert c.post("/control", headers=headers).status_code == 200
        with c.websocket_connect("ws://127.0.0.1:8765/events", headers=headers) as ws:
            assert ws.receive_json()["type"] == "hello"


def test_unknown_host_and_originless_cross_site_controls_are_rejected():
    with client() as c:
        assert (
            c.post("/control", headers={"Host": "foreign.example", "Origin": "http://foreign.example"}).status_code
            == 400
        )
        assert c.post("/control", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
