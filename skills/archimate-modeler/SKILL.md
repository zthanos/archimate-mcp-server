---
name: archimate-modeler
description: Create, extend, validate, repair, view, and export ArchiMate 3.1 models from plain-language architecture descriptions, code summaries, or existing model JSON. Use when the task is to turn system or business architecture into a valid ArchiMate model, revise an existing model with natural-language changes, diagnose invalid relationships or weak structure, generate importable views/XML, or derive architecture facts from code for modeling.
---

# ArchiMate Modeler

Build a valid ArchiMate model first, then improve presentation and export.

Use the MCP tools in a validation-first loop:

1. Extract or load facts
2. Validate the model or facts
3. Repair obvious issues
4. Generate views when the structure is stable
5. Export XML only after validation succeeds

Treat the workflow as:

`source input -> facts/model -> validate -> repair if needed -> generate views -> export`

## Choose The Right Entry Point

For plain-text architecture descriptions, call `extract_archimate_facts_from_text`.

For source-code-derived descriptions, service inventories, README architecture summaries, or dependency summaries, call `extract_archimate_facts_from_code_summary`.

For an existing canonical model JSON payload, start with `validate_archimate_model` if it already includes `model`, `elements`, and `relationships`. Start with `validate_archimate_facts` if the payload only contains `elements` and `relationships`.

For a quick scaffold or demo, call `generate_archimate_sample_model`.

## Operate In Update Mode By Default

If the conversation already contains a model, prefer updating it instead of regenerating from scratch.

Pass the current model through `existing_model_json` when using extraction tools so newly extracted facts merge into the working model.

For user requests like:

- "add a database"
- "replace Kubernetes with a VM"
- "fix the invalid relationships"
- "connect the portal to the customer record"

apply the smallest safe change to the existing model, then validate again.

Ask for clarification only when the instruction is genuinely ambiguous and multiple plausible model changes would materially differ.

## Use These MCP Tools

### Extraction

- `extract_archimate_facts_from_text`
- `extract_archimate_facts_from_code_summary`

### Validation

- `validate_archimate_facts`
- `validate_archimate_model`

### Repair And Review

- `normalize_relationship_types`
- `suggest_missing_relationships`
- `detect_architecture_smells`

### View Generation

- `generate_archimate_views`

### Export

- `generate_archimate_exchange_xml`
- `generate_archimate_exchange_file`

## Follow These Rules

- Validate before generating exports intended for handoff or import.
- Never claim a model is valid unless validation returned success.
- Prefer specific ArchiMate relationship types over `Association` when the semantics are clear.
- Keep IDs stable when iterating on an existing model.
- Do not invent elements, layers, or relationships that are not supported by the input or by ArchiMate rules.
- Do not expose raw JSON unless the user asks for it or the workflow requires it.
- Explain the meaningful modeling decisions when you change an existing model.

## Handle Validation Failures

If validation fails, do not proceed straight to export.

Instead:

1. Summarize the issue in plain language
2. Propose or apply the smallest valid fix
3. Re-run validation
4. Only continue to views/export after the model is valid

Use `normalize_relationship_types` when the issue looks like the wrong relationship kind.

Use `suggest_missing_relationships` when the model is structurally thin but not obviously invalid.

Use `detect_architecture_smells` when the model is valid but weak, incomplete, or suspicious.

## Read References Only When Needed

Read [references/archimate-rules.md](references/archimate-rules.md) when you need allowed element types, relationship types, or common correction patterns.

Read [references/example-models.md](references/example-models.md) when you need a modeling pattern, naming convention, or a concrete structural example to imitate.

## Preferred Working Patterns

### Create From Text

1. Extract facts from the text
2. Validate the extracted facts
3. If needed, repair relationships or structure
4. Generate views
5. Export only if requested

### Create From Code Summary

1. Extract facts from the code summary
2. Validate the extracted facts
3. Review for missing services, data objects, or runtime/deployment nodes
4. Generate views
5. Export only if requested

### Update Existing Model

1. Start from the current model JSON
2. Merge or edit only the requested changes
3. Validate the updated model
4. Regenerate views if the structure changed
5. Export only if requested

### Repair Existing Model

1. Validate the current model or facts
2. Normalize relationship types if needed
3. Check for missing relationships or smells if the model is still weak
4. Validate again
5. Generate views or export after the model stabilizes

## Output Style

Keep responses concise and structured.

When modifying a model, state:

- what changed
- why it changed
- whether the model validated
- whether views or export were generated

If export is requested, prefer returning the file path or XML result rather than a long explanation.
