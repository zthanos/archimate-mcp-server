from __future__ import annotations

import json
from pathlib import Path
import os

from mcp.server.fastmcp import FastMCP

from .builders import build_model_with_default_view
from .exporter import export_archimate_exchange_xml
from .llm import call_llm
from .models import ArchimateModel, Element, Relationship
from .validation import ValidationError, validate_model


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


mcp = FastMCP(
    "archimate-mcp-server",
    host=os.getenv("FASTMCP_HOST", "127.0.0.1").strip() or "127.0.0.1",
    port=_env_int("FASTMCP_PORT", 8000),
    streamable_http_path=os.getenv("FASTMCP_STREAMABLE_HTTP_PATH", "/mcp").strip() or "/mcp",
)


# ---------------------------------------------------------------------------
# Existing tools
# ---------------------------------------------------------------------------

@mcp.tool()
def validate_archimate_model(model_json: str) -> dict:
    """Validate a canonical ArchiMate model JSON payload."""
    data = json.loads(model_json)
    model = ArchimateModel.model_validate(data)
    errors = validate_model(model)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


@mcp.tool()
def generate_archimate_exchange_xml(model_json: str) -> dict:
    """Build missing default view(s), validate the model, and export ArchiMate exchange XML."""
    data = json.loads(model_json)
    model = ArchimateModel.model_validate(data)
    model = build_model_with_default_view(model)
    xml = export_archimate_exchange_xml(model)
    return {
        "model_id": model.model.id,
        "view_count": len(model.views),
        "xml": xml,
    }


@mcp.tool()
def generate_archimate_exchange_file(model_json: str, output_path: str) -> dict:
    """Build missing default view(s), validate the model, export ArchiMate XML, and save it to a file."""
    data = json.loads(model_json)
    model = ArchimateModel.model_validate(data)
    model = build_model_with_default_view(model)
    xml = export_archimate_exchange_xml(model)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")

    return {
        "ok": True,
        "path": str(path.resolve()),
        "model_id": model.model.id,
    }


@mcp.tool()
def generate_archimate_sample_model() -> dict:
    """Return a sample canonical JSON model payload for quick testing."""
    sample_path = Path(__file__).resolve().parent / "examples" / "sample_model.json"
    sample_json = sample_path.read_text(encoding="utf-8")
    return {
        "sample_model_json": sample_json,
    }


# ---------------------------------------------------------------------------
# New extraction / composition tools
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM_PROMPT = """\
You are an ArchiMate 3.1 modelling assistant.

Your job is to extract ArchiMate facts from the input and return ONLY a JSON object — \
no prose, no markdown fences, no explanation.

The JSON must match this schema exactly:
{
  "elements": [
    {"id": "<slug>", "type": "<ElementType>", "name": "<name>"}
  ],
  "relationships": [
    {"id": "<slug>", "type": "<RelationshipType>", "source": "<element_id>", "target": "<element_id>", "name": "<optional>"}
  ]
}

Valid ElementType values:
  BusinessActor, BusinessProcess,
  ApplicationComponent, ApplicationService, DataObject,
  Node, Device, SystemSoftware

Valid RelationshipType values:
  Serving, Access, Assignment, Realization,
  Composition, Aggregation, Association, Flow, Triggering

Rules:
- Generate stable lowercase slug IDs (e.g. "app_portal", "rel_serving_1")
- Only include relationships between elements you have defined
- Do NOT invent elements that are not implied by the input
- Return valid JSON only
"""

_TEXT_USER_PROMPT = "Extract ArchiMate facts from the following text:\n\n{input}"
_CODE_USER_PROMPT = """\
Extract ArchiMate facts from the following code / architecture summary.
Focus on: components, services, data stores, runtime infrastructure, \
and the relationships between them.\n\n{input}"""


def _extract_facts(raw_input: str, user_prompt_template: str, existing_model_json: str | None) -> dict:
    """Shared extraction logic for text and code summary inputs."""
    user_prompt = user_prompt_template.format(input=raw_input)
    raw_json = call_llm(_EXTRACTION_SYSTEM_PROMPT, user_prompt)

    # Parse and normalise
    try:
        facts = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"LLM returned invalid JSON: {exc}", "raw": raw_json}

    extracted_elements = facts.get("elements", [])
    extracted_relationships = facts.get("relationships", [])

    # Merge with existing model if provided
    if existing_model_json:
        existing_data = json.loads(existing_model_json)
        existing_model = ArchimateModel.model_validate(existing_data)

        existing_element_ids = {e.id for e in existing_model.elements}
        existing_rel_ids = {r.id for r in existing_model.relationships}

        for el in extracted_elements:
            if el["id"] not in existing_element_ids:
                existing_model.elements.append(Element.model_validate(el))

        for rel in extracted_relationships:
            if rel["id"] not in existing_rel_ids:
                existing_model.relationships.append(Relationship.model_validate(rel))

        merged_data = existing_model.model_dump()
    else:
        merged_data = None

    # Partial validation — only check the extracted facts in isolation
    partial_model_data = {
        "model": {"id": "extracted", "name": "Extracted Facts"},
        "elements": extracted_elements,
        "relationships": extracted_relationships,
    }
    try:
        partial_model = ArchimateModel.model_validate(partial_model_data)
        validation_errors = validate_model(partial_model)
    except Exception as exc:
        validation_errors = [str(exc)]

    return {
        "ok": True,
        "extracted": {
            "elements": extracted_elements,
            "relationships": extracted_relationships,
        },
        "validation_warnings": validation_errors,
        "merged_model_json": json.dumps(merged_data) if merged_data else None,
    }


@mcp.tool()
def extract_archimate_facts_from_text(
    text: str,
    existing_model_json: str | None = None,
) -> dict:
    """
    Extract ArchiMate elements and relationships from a free-text description.

    Optionally merges the extracted facts into an existing model (pass its JSON as
    existing_model_json). Returns the extracted facts, any validation warnings, and
    the merged model JSON if a base model was provided.
    """
    return _extract_facts(text, _TEXT_USER_PROMPT, existing_model_json)


@mcp.tool()
def extract_archimate_facts_from_code_summary(
    code_or_summary: str,
    existing_model_json: str | None = None,
) -> dict:
    """
    Extract ArchiMate elements and relationships from source code or an architecture
    code summary (e.g. a README, a list of services, a dependency graph description).

    Optionally merges the extracted facts into an existing model (pass its JSON as
    existing_model_json). Returns the extracted facts, any validation warnings, and
    the merged model JSON if a base model was provided.
    """
    return _extract_facts(code_or_summary, _CODE_USER_PROMPT, existing_model_json)


@mcp.tool()
def validate_archimate_facts(facts_json: str) -> dict:
    """
    Validate a partial or complete ArchiMate facts payload (elements + relationships).

    Accepts either a full ArchimateModel JSON or a partial payload with just
    'elements' and 'relationships' keys.
    """
    data = json.loads(facts_json)

    # Accept partial payloads (no model/views required)
    if "model" not in data:
        data["model"] = {"id": "validation_only", "name": "Validation Only"}

    model = ArchimateModel.model_validate(data)
    errors = validate_model(model)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "element_count": len(model.elements),
        "relationship_count": len(model.relationships),
    }


@mcp.tool()
def generate_archimate_views(model_json: str) -> dict:
    """
    Generate default ArchiMate view(s) for a model that has no views yet,
    and return the enriched model JSON (with views) without exporting to XML.

    Use this to inspect or further modify the layout before exporting.
    """
    data = json.loads(model_json)
    model = ArchimateModel.model_validate(data)
    model = build_model_with_default_view(model)
    return {
        "model_json": model.model_dump_json(),
        "view_count": len(model.views),
        "view_ids": [v.id for v in model.views],
    }


# ---------------------------------------------------------------------------
# Architecture repair tools
# ---------------------------------------------------------------------------

_SUGGEST_RELATIONSHIPS_SYSTEM_PROMPT = """\
You are an ArchiMate 3.1 expert.

Given a list of ArchiMate elements and their existing relationships, suggest \
relationships that are likely missing based on standard ArchiMate patterns and \
best practices.

Return ONLY a JSON object — no prose, no markdown fences:
{
  "suggestions": [
    {
      "source": "<element_id>",
      "target": "<element_id>",
      "type": "<RelationshipType>",
      "rationale": "<one sentence why>"
    }
  ]
}

Valid RelationshipType values:
  Serving, Access, Assignment, Realization,
  Composition, Aggregation, Association, Flow, Triggering

Rules:
- Only suggest relationships between elements that exist in the input
- Only suggest relationships that are valid per ArchiMate 3.1 metamodel
- Do not suggest relationships that already exist
- Prefer the most semantically precise relationship type
"""

_NORMALIZE_RELATIONSHIPS_SYSTEM_PROMPT = """\
You are an ArchiMate 3.1 expert.

Given a list of ArchiMate elements and relationships, identify any relationships \
whose type appears incorrect or imprecise according to ArchiMate 3.1 rules.

Return ONLY a JSON object — no prose, no markdown fences:
{
  "corrections": [
    {
      "relationship_id": "<id>",
      "current_type": "<type>",
      "suggested_type": "<type>",
      "rationale": "<one sentence why>"
    }
  ]
}

If all relationships are correctly typed, return: {"corrections": []}
"""

_DETECT_SMELLS_SYSTEM_PROMPT = """\
You are an ArchiMate 3.1 expert reviewing an architecture model for quality issues.

Analyse the provided model and detect architecture smells such as:
- Isolated elements (no relationships)
- Elements assigned to the wrong ArchiMate layer
- Circular dependencies
- Missing realization chains (e.g. ApplicationComponent with no ApplicationService)
- Over-connected elements (god components)
- Broken cross-layer patterns

Return ONLY a JSON object — no prose, no markdown fences:
{
  "smells": [
    {
      "severity": "error" | "warning" | "info",
      "affected_ids": ["<id>", ...],
      "description": "<one sentence>",
      "suggestion": "<one sentence fix>"
    }
  ]
}

If no smells are found, return: {"smells": []}
"""


def _model_summary_for_prompt(model: ArchimateModel) -> str:
    """Render a compact model summary suitable for a repair prompt."""
    lines = ["Elements:"]
    for el in model.elements:
        lines.append(f"  {el.id} | {el.type} | {el.name}")
    lines.append("Relationships:")
    for rel in model.relationships:
        name_part = f" ({rel.name})" if rel.name else ""
        lines.append(f"  {rel.id} | {rel.source} -[{rel.type}]-> {rel.target}{name_part}")
    return "\n".join(lines)


@mcp.tool()
def suggest_missing_relationships(model_json: str) -> dict:
    """
    Analyse an ArchiMate model and suggest relationships that are likely missing
    based on standard ArchiMate 3.1 patterns.

    Returns a list of suggestions with source, target, type, and rationale.
    """
    data = json.loads(model_json)
    model = ArchimateModel.model_validate(data)
    summary = _model_summary_for_prompt(model)

    raw = call_llm(_SUGGEST_RELATIONSHIPS_SYSTEM_PROMPT, summary)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"LLM returned invalid JSON: {exc}", "raw": raw}

    return {
        "ok": True,
        "suggestion_count": len(result.get("suggestions", [])),
        "suggestions": result.get("suggestions", []),
    }


@mcp.tool()
def normalize_relationship_types(model_json: str) -> dict:
    """
    Review the relationship types in an ArchiMate model and suggest corrections
    where the type appears semantically incorrect or imprecise.

    Returns a list of corrections with the current type, suggested type, and rationale.
    If the model is well-typed, returns an empty corrections list.
    """
    data = json.loads(model_json)
    model = ArchimateModel.model_validate(data)
    summary = _model_summary_for_prompt(model)

    raw = call_llm(_NORMALIZE_RELATIONSHIPS_SYSTEM_PROMPT, summary)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"LLM returned invalid JSON: {exc}", "raw": raw}

    return {
        "ok": True,
        "correction_count": len(result.get("corrections", [])),
        "corrections": result.get("corrections", []),
    }


@mcp.tool()
def detect_architecture_smells(model_json: str) -> dict:
    """
    Detect architecture quality issues (smells) in an ArchiMate model.

    Checks for: isolated elements, wrong-layer assignments, circular dependencies,
    missing realization chains, over-connected components, and broken cross-layer
    patterns.

    Returns a list of smells with severity (error/warning/info), affected element
    IDs, description, and a suggested fix.
    """
    data = json.loads(model_json)
    model = ArchimateModel.model_validate(data)

    # Run deterministic checks first (fast, no LLM needed)
    deterministic_smells = _detect_deterministic_smells(model)

    # Then run LLM-based semantic checks
    summary = _model_summary_for_prompt(model)
    raw = call_llm(_DETECT_SMELLS_SYSTEM_PROMPT, summary)
    try:
        llm_result = json.loads(raw)
        llm_smells = llm_result.get("smells", [])
    except json.JSONDecodeError:
        llm_smells = []

    all_smells = deterministic_smells + llm_smells
    errors = [s for s in all_smells if s["severity"] == "error"]
    warnings = [s for s in all_smells if s["severity"] == "warning"]
    infos = [s for s in all_smells if s["severity"] == "info"]

    return {
        "ok": True,
        "smell_count": len(all_smells),
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
    }


def _detect_deterministic_smells(model: ArchimateModel) -> list[dict]:
    """Fast, rule-based smell detection that doesn't require an LLM call."""
    smells: list[dict] = []

    # Build connectivity index
    connected: set[str] = set()
    for rel in model.relationships:
        connected.add(rel.source)
        connected.add(rel.target)

    # 1. Isolated elements
    for el in model.elements:
        if el.id not in connected:
            smells.append({
                "severity": "warning",
                "affected_ids": [el.id],
                "description": f"Element '{el.name}' ({el.type}) has no relationships.",
                "suggestion": "Connect it to the architecture or remove it if unused.",
            })

    # 2. Circular dependencies (direct A→B→A cycles)
    rel_pairs: set[tuple[str, str]] = {(r.source, r.target) for r in model.relationships}
    for src, tgt in rel_pairs:
        if (tgt, src) in rel_pairs:
            smells.append({
                "severity": "info",
                "affected_ids": [src, tgt],
                "description": f"Bidirectional relationship between '{src}' and '{tgt}'.",
                "suggestion": "Review if both directions are intentional or if one should be removed.",
            })

    # 3. ApplicationComponent with no ApplicationService (missing realization)
    app_components = {e.id for e in model.elements if e.type == "ApplicationComponent"}
    realizes_targets = {
        r.target for r in model.relationships
        if r.type == "Realization" and r.source in app_components
    }
    app_services = {e.id for e in model.elements if e.type == "ApplicationService"}
    for comp_id in app_components:
        if comp_id not in {r.source for r in model.relationships if r.type == "Realization"}:
            smells.append({
                "severity": "info",
                "affected_ids": [comp_id],
                "description": f"ApplicationComponent '{comp_id}' does not realize any ApplicationService.",
                "suggestion": "Add a Realization relationship to the ApplicationService it implements.",
            })

    # 4. ApplicationService with no serving relationship
    for svc_id in app_services:
        if svc_id not in {r.source for r in model.relationships if r.type == "Serving"}:
            smells.append({
                "severity": "info",
                "affected_ids": [svc_id],
                "description": f"ApplicationService '{svc_id}' does not serve any component.",
                "suggestion": "Add a Serving relationship to the ApplicationComponent that uses it.",
            })

    return smells


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        transport = os.getenv("ARCHIMATE_MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
        mount_path = os.getenv("ARCHIMATE_MCP_MOUNT_PATH", "").strip() or None
        mcp.run(transport=transport, mount_path=mount_path)
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
