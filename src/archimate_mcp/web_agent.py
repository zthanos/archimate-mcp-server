from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "archimate-modeler" / "SKILL.md"
WEB_OUTPUT_DIR = REPO_ROOT / "out" / "web"


@dataclass
class ToolLog:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class ChatSessionState:
    session_id: str
    messages: list[dict[str, str]] = field(default_factory=list)
    current_model_json: str | None = None
    last_export_path: Path | None = None


class ChatAgent:
    def __init__(self, mcp_url: str):
        self.mcp_url = mcp_url
        self.skill_text = SKILL_PATH.read_text(encoding="utf-8")

    async def run(self, state: ChatSessionState, user_message: str) -> dict[str, Any]:
        final_result = None
        async for event in self.run_stream(state, user_message):
            if event["type"] == "final":
                final_result = event["data"]

        assert final_result is not None
        return final_result

    async def run_stream(self, state: ChatSessionState, user_message: str) -> AsyncIterator[dict[str, Any]]:
        state.messages.append({"role": "user", "content": user_message})
        architecture_text = self._extract_architecture_text(user_message)
        wants_export = self._wants_export(user_message)
        wants_views = self._wants_views(user_message) or wants_export
        wants_tool_list = self._wants_tool_list(user_message)

        planned_tools = self._build_plan(wants_views=wants_views, wants_export=wants_export)
        tool_logs: list[ToolLog] = []
        yield {"type": "plan", "data": {"planned_tools": planned_tools}}

        async with streamable_http_client(self.mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                extract_result = await self._call_tool(
                    session,
                    "extract_archimate_facts_from_text",
                    {
                        "text": architecture_text,
                        "existing_model_json": state.current_model_json,
                    },
                    tool_logs,
                )
                yield {"type": "tool", "data": self._tool_log_payload(tool_logs[-1])}

                if not extract_result.get("ok", False):
                    yield {
                        "type": "final",
                        "data": self._response(
                            state,
                            wants_tool_list,
                            planned_tools,
                            tool_logs,
                            "The extraction tool returned an error, so I stopped before validation/export.",
                        ),
                    }
                    return

                yield {
                    "type": "status",
                    "data": {
                        "message": "Extraction completed. Building a working model and validating it.",
                    },
                }

                working_model_json = self._build_working_model_json(extract_result, state.current_model_json)

                validation_result = await self._call_tool(
                    session,
                    "validate_archimate_facts",
                    {"facts_json": working_model_json},
                    tool_logs,
                )
                yield {"type": "tool", "data": self._tool_log_payload(tool_logs[-1])}

                if not validation_result.get("valid", False):
                    state.current_model_json = working_model_json
                    yield {
                        "type": "final",
                        "data": self._response(
                            state,
                            wants_tool_list,
                            planned_tools,
                            tool_logs,
                            "The model was extracted but validation failed, so I did not generate views or export XML.",
                        ),
                    }
                    return

                state.current_model_json = working_model_json
                generated_view_count = 0

                if wants_views:
                    yield {
                        "type": "status",
                        "data": {
                            "message": "Validation passed. Generating views.",
                        },
                    }
                    views_result = await self._call_tool(
                        session,
                        "generate_archimate_views",
                        {"model_json": working_model_json},
                        tool_logs,
                    )
                    yield {"type": "tool", "data": self._tool_log_payload(tool_logs[-1])}
                    state.current_model_json = views_result["model_json"]
                    generated_view_count = views_result["view_count"]

                export_relpath: str | None = None
                if wants_export:
                    yield {
                        "type": "status",
                        "data": {
                            "message": "Views are ready. Exporting ArchiMate XML.",
                        },
                    }
                    export_path = self._next_export_path(state.session_id)
                    export_result = await self._call_tool(
                        session,
                        "generate_archimate_exchange_file",
                        {
                            "model_json": state.current_model_json,
                            "output_path": str(export_path),
                        },
                        tool_logs,
                    )
                    yield {"type": "tool", "data": self._tool_log_payload(tool_logs[-1])}
                    state.last_export_path = Path(export_result["path"])
                    export_relpath = state.last_export_path.name

        final_summary = self._summarize(
            tool_logs=tool_logs,
            validation_result=validation_result,
            generated_view_count=generated_view_count,
            export_relpath=export_relpath,
        )
        yield {
            "type": "final",
            "data": self._response(state, wants_tool_list, planned_tools, tool_logs, final_summary, export_relpath),
        }

    def _tool_log_payload(self, log: ToolLog) -> dict[str, Any]:
        return {
            "name": log.name,
            "arguments": log.arguments,
            "result": log.result,
            "error": log.error,
        }

    def _response(
        self,
        state: ChatSessionState,
        wants_tool_list: bool,
        planned_tools: list[str],
        tool_logs: list[ToolLog],
        summary: str,
        export_relpath: str | None = None,
    ) -> dict[str, Any]:
        content = []
        if wants_tool_list:
            content.append("Planned tools: " + ", ".join(planned_tools))
        content.append(summary)
        assistant_text = "\n\n".join(content)
        state.messages.append({"role": "assistant", "content": assistant_text})

        return {
            "assistant_message": assistant_text,
            "planned_tools": planned_tools,
            "tool_logs": [
                {
                    "name": log.name,
                    "arguments": log.arguments,
                    "result": log.result,
                    "error": log.error,
                }
                for log in tool_logs
            ],
            "session_id": state.session_id,
            "export_path": f"/downloads/{export_relpath}" if export_relpath else None,
            "skill_path": str(SKILL_PATH),
            "mcp_url": self.mcp_url,
        }

    async def _call_tool(
        self,
        session: ClientSession,
        name: str,
        arguments: dict[str, Any],
        tool_logs: list[ToolLog],
    ) -> dict[str, Any]:
        log = ToolLog(name=name, arguments=arguments)
        tool_logs.append(log)
        result = await session.call_tool(name, arguments)
        payload = self._tool_payload(result)
        if result.isError:
            log.error = json.dumps(payload, ensure_ascii=False)
            return {"ok": False, "error": log.error}
        log.result = payload
        return payload

    def _tool_payload(self, result: Any) -> dict[str, Any]:
        if getattr(result, "structuredContent", None) is not None:
            return result.structuredContent

        content = getattr(result, "content", None) or []
        if content and hasattr(content[0], "text"):
            try:
                return json.loads(content[0].text)
            except json.JSONDecodeError:
                return {"text": content[0].text}

        return {}

    def _build_plan(self, *, wants_views: bool, wants_export: bool) -> list[str]:
        plan = [
            "extract_archimate_facts_from_text",
            "validate_archimate_facts",
        ]
        if wants_views:
            plan.append("generate_archimate_views")
        if wants_export:
            plan.append("generate_archimate_exchange_file")
        return plan

    def _build_working_model_json(self, extract_result: dict[str, Any], existing_model_json: str | None) -> str:
        merged = extract_result.get("merged_model_json")
        if merged:
            return merged

        payload = {
            "model": {
                "id": "web_chat_model",
                "name": "Web Chat Model",
            },
            "elements": extract_result["extracted"]["elements"],
            "relationships": extract_result["extracted"]["relationships"],
        }

        if existing_model_json:
            try:
                existing = json.loads(existing_model_json)
                payload["model"]["id"] = existing.get("model", {}).get("id", payload["model"]["id"])
                payload["model"]["name"] = existing.get("model", {}).get("name", payload["model"]["name"])
            except json.JSONDecodeError:
                pass

        return json.dumps(payload)

    def _summarize(
        self,
        *,
        tool_logs: list[ToolLog],
        validation_result: dict[str, Any],
        generated_view_count: int,
        export_relpath: str | None,
    ) -> str:
        extracted = next((log.result for log in tool_logs if log.name == "extract_archimate_facts_from_text"), None) or {}
        element_count = len(extracted.get("extracted", {}).get("elements", []))
        relationship_count = len(extracted.get("extracted", {}).get("relationships", []))
        parts = [
            f"Built a model with {element_count} element(s) and {relationship_count} relationship(s).",
            f"Validation: {'passed' if validation_result.get('valid') else 'failed'} with {len(validation_result.get('errors', []))} error(s).",
        ]
        if generated_view_count:
            parts.append(f"Generated {generated_view_count} view(s).")
        if export_relpath:
            parts.append(f"Exported XML: /downloads/{export_relpath}")
        return " ".join(parts)

    def _next_export_path(self, session_id: str) -> Path:
        WEB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return WEB_OUTPUT_DIR / f"{session_id}-{timestamp}.xml"

    def _extract_architecture_text(self, message: str) -> str:
        quoted = re.findall(r'"([^\"]+)"', message, flags=re.DOTALL)
        if quoted:
            return quoted[-1].strip()

        colon_match = re.search(r":\s*(.+)$", message, flags=re.DOTALL)
        if colon_match:
            return colon_match.group(1).strip()

        return message.strip()

    def _wants_export(self, message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in ("export", "xml", "file"))

    def _wants_views(self, message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in ("view", "diagram", "render"))

    def _wants_tool_list(self, message: str) -> bool:
        lowered = message.lower()
        return "list the tools" in lowered or "first list the tools" in lowered


def new_session() -> ChatSessionState:
    return ChatSessionState(session_id=uuid4().hex[:12])
