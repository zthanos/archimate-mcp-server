from __future__ import annotations

import json

from archimate_mcp.webapp import _sse_event


def test_sse_event_formats_named_event() -> None:
    payload = {"ok": True, "message": "hello"}

    result = _sse_event("status", payload)

    assert result.startswith("event: status\n")
    assert f"data: {json.dumps(payload, ensure_ascii=False)}\n\n" in result
