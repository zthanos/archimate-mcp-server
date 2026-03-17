from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .builders import build_model_with_default_view
from .exporter import export_archimate_exchange_xml
from .models import ArchimateModel
from .validation import ValidationError, validate_model
from .layout import (
    generate_application_cooperation_view,
    generate_technology_view,
    generate_integration_view,
)


def _load_model(path: str) -> ArchimateModel:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ArchimateModel.model_validate(data)


def _write_output(content: str, output: str | None, label: str) -> None:
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        print(f"Wrote {out}")
    else:
        print(content)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    model = _load_model(args.input)
    errors = validate_model(model)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    print("Model is valid")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    model = _load_model(args.input)
    try:
        model = build_model_with_default_view(model)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    xml = export_archimate_exchange_xml(model)
    _write_output(xml, args.output, "export")
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    """Suggest missing relationships using the LLM."""
    from .server import suggest_missing_relationships
    model = _load_model(args.input)
    result = suggest_missing_relationships(model.model_dump_json())
    if not result["ok"]:
        print(result.get("error", "Unknown error"), file=sys.stderr)
        return 1
    suggestions = result["suggestions"]
    if not suggestions:
        print("No missing relationships suggested.")
        return 0
    print(f"{len(suggestions)} suggestion(s):\n")
    for s in suggestions:
        print(f"  {s['source']} -[{s['type']}]-> {s['target']}")
        print(f"  Rationale: {s['rationale']}\n")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    """Suggest relationship type corrections using the LLM."""
    from .server import normalize_relationship_types
    model = _load_model(args.input)
    result = normalize_relationship_types(model.model_dump_json())
    if not result["ok"]:
        print(result.get("error", "Unknown error"), file=sys.stderr)
        return 1
    corrections = result["corrections"]
    if not corrections:
        print("All relationship types look correct.")
        return 0
    print(f"{len(corrections)} correction(s):\n")
    for c in corrections:
        print(f"  {c['relationship_id']}: {c['current_type']} -> {c['suggested_type']}")
        print(f"  Rationale: {c['rationale']}\n")
    return 0


def cmd_smells(args: argparse.Namespace) -> int:
    """Detect architecture smells (deterministic + LLM)."""
    from .server import detect_architecture_smells
    model = _load_model(args.input)
    result = detect_architecture_smells(model.model_dump_json())

    total = result["smell_count"]
    if total == 0:
        print("No architecture smells detected.")
        return 0

    print(f"{total} smell(s) found:\n")
    for severity, items in [("errors", result["errors"]), ("warnings", result["warnings"]), ("infos", result["infos"])]:
        for s in items:
            ids = ", ".join(s["affected_ids"])
            print(f"  [{severity.upper()[:-1]}] {s['description']}")
            print(f"  Affected: {ids}")
            print(f"  Fix: {s['suggestion']}\n")

    # Return non-zero if there are errors
    return 1 if result["errors"] else 0


def cmd_view(args: argparse.Namespace) -> int:
    """Generate a specific view and export it as XML."""
    model = _load_model(args.input)

    VIEW_GENERATORS = {
        "application": (
            lambda m: build_model_with_default_view(m),
            None,  # handled by builder
        ),
        "cooperation": (
            lambda m: generate_application_cooperation_view(
                m, "view_application_cooperation", "Application Cooperation View"
            ),
            "cooperation",
        ),
        "technology": (
            lambda m: generate_technology_view(
                m, "view_technology", "Technology View"
            ),
            "technology",
        ),
        "integration": (
            lambda m: generate_integration_view(
                m, "view_integration", "Integration View"
            ),
            "integration",
        ),
    }

    if args.view not in VIEW_GENERATORS:
        print(f"Unknown view type '{args.view}'. Choose from: {', '.join(VIEW_GENERATORS)}", file=sys.stderr)
        return 1

    generator, view_id = VIEW_GENERATORS[args.view]

    try:
        if args.view == "application":
            model = build_model_with_default_view(model)
        else:
            view = generator(model)
            if not view.nodes:
                print(f"View '{args.view}' has no nodes — model may lack the required element types.", file=sys.stderr)
                return 1
            model.views = [view]
            errors = validate_model(model)
            if errors:
                for err in errors:
                    print(err, file=sys.stderr)
                return 1
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    xml = export_archimate_exchange_xml(model)
    _write_output(xml, args.output, args.view)
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArchiMate MCP CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # validate
    p = sub.add_parser("validate", help="Validate canonical ArchiMate JSON")
    p.add_argument("input", help="Path to JSON model input")
    p.set_defaults(func=cmd_validate)

    # export
    p = sub.add_parser("export", help="Export ArchiMate exchange XML (all views)")
    p.add_argument("input", help="Path to JSON model input")
    p.add_argument("--output", help="Optional output XML path")
    p.set_defaults(func=cmd_export)

    # view
    p = sub.add_parser("view", help="Generate a specific view and export as XML")
    p.add_argument("input", help="Path to JSON model input")
    p.add_argument("--type", dest="view", default="application",
                   choices=["application", "cooperation", "technology", "integration"],
                   help="View type to generate (default: application)")
    p.add_argument("--output", help="Optional output XML path")
    p.set_defaults(func=cmd_view)

    # suggest
    p = sub.add_parser("suggest", help="Suggest missing relationships (LLM-assisted)")
    p.add_argument("input", help="Path to JSON model input")
    p.set_defaults(func=cmd_suggest)

    # normalize
    p = sub.add_parser("normalize", help="Suggest relationship type corrections (LLM-assisted)")
    p.add_argument("input", help="Path to JSON model input")
    p.set_defaults(func=cmd_normalize)

    # smells
    p = sub.add_parser("smells", help="Detect architecture smells")
    p.add_argument("input", help="Path to JSON model input")
    p.set_defaults(func=cmd_smells)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()