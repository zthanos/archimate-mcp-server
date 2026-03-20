from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from .web_agent import WEB_OUTPUT_DIR, ChatAgent, ChatSessionState, new_session


STATIC_DIR = Path(__file__).resolve().parent / "web"
INDEX_PATH = STATIC_DIR / "index.html"
APP_JS_PATH = STATIC_DIR / "app.js"
STYLES_PATH = STATIC_DIR / "styles.css"

SESSIONS: dict[str, ChatSessionState] = {}


async def homepage(_: Request):
    return FileResponse(INDEX_PATH)


async def app_js(_: Request):
    return FileResponse(APP_JS_PATH, media_type="application/javascript")


async def styles_css(_: Request):
    return FileResponse(STYLES_PATH, media_type="text/css")


async def health(_: Request):
    return JSONResponse({"ok": True})


async def create_session(_: Request):
    session = new_session()
    SESSIONS[session.session_id] = session
    return JSONResponse({"session_id": session.session_id})


async def chat(request: Request):
    body = await request.json()
    session_id = body.get("session_id") or new_session().session_id
    message = str(body.get("message", "")).strip()
    stream = bool(body.get("stream"))

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    state = SESSIONS.setdefault(session_id, ChatSessionState(session_id=session_id))
    agent = ChatAgent(os.getenv("ARCHIMATE_MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"))

    if stream:
        async def event_stream() -> AsyncIterator[str]:
            try:
                async for event in agent.run_stream(state, message):
                    yield _sse_event(event["type"], event["data"])
            except Exception as exc:
                yield _sse_event(
                    "error",
                    {
                        "error": str(exc),
                        "session_id": session_id,
                        "mcp_url": os.getenv("ARCHIMATE_MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
                    },
                )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        result = await agent.run(state, message)
    except Exception as exc:
        return JSONResponse(
            {
                "error": str(exc),
                "session_id": session_id,
                "mcp_url": os.getenv("ARCHIMATE_MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
            },
            status_code=500,
        )

    return JSONResponse(result)


def _sse_event(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def download(request: Request):
    filename = request.path_params["filename"]
    path = (WEB_OUTPUT_DIR / filename).resolve()
    if WEB_OUTPUT_DIR.resolve() not in path.parents:
        return JSONResponse({"error": "invalid path"}, status_code=400)
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="application/xml", filename=path.name)


app = Starlette(
    debug=False,
    routes=[
        Route("/", homepage),
        Route("/app.js", app_js),
        Route("/styles.css", styles_css),
        Route("/health", health),
        Route("/api/session", create_session, methods=["POST"]),
        Route("/api/chat", chat, methods=["POST"]),
        Route("/downloads/{filename:path}", download),
    ],
)


def main() -> None:
    host = os.getenv("ARCHIMATE_MCP_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("ARCHIMATE_MCP_WEB_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
