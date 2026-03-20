from __future__ import annotations

from archimate_mcp.web_agent import ChatAgent


def test_extract_architecture_text_prefers_last_quoted_block() -> None:
    agent = ChatAgent("http://127.0.0.1:8000/mcp")

    result = agent._extract_architecture_text(
        'Create a model from this plain text: "first" and then use "Customer uses app"'
    )

    assert result == "Customer uses app"


def test_build_plan_adds_export_and_views_steps() -> None:
    agent = ChatAgent("http://127.0.0.1:8000/mcp")

    assert agent._build_plan(wants_views=False, wants_export=False) == [
        "extract_archimate_facts_from_text",
        "validate_archimate_facts",
    ]
    assert agent._build_plan(wants_views=True, wants_export=True) == [
        "extract_archimate_facts_from_text",
        "validate_archimate_facts",
        "generate_archimate_views",
        "generate_archimate_exchange_file",
    ]
