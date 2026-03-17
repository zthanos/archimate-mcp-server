---
name: archimate-diagrams
description: Create, update, validate, repair, generate views, and export ArchiMate models from plain text, code, or structured input.
---

# ArchiMate Diagram Skill

This skill enables the agent to create, update, validate, repair, generate views for, and export ArchiMate models.

It supports:
- plain text → ArchiMate model
- iterative corrections using natural language
- validation and repair of models
- generation of ArchiMate views
- export to Open Exchange Format (Archi-compatible XML)

---

# When to Use This Skill

Use this skill when the user wants to:

- create an ArchiMate model or diagram
- update or correct an existing model
- validate or fix ArchiMate relationships or elements
- generate views for visualization
- export a model for use in Archi or other EA tools

Do NOT use this skill for:
- general ArchiMate theory questions
- comparisons (e.g. ArchiMate vs C4)
- documentation without modeling intent

---

# Supported Inputs

The user may provide:

1. Plain text description
   Example:
   "Customer uses a portal that calls a payment service"

2. Code (COBOL, Java, Python, etc.)
   → extract architecture elements and flows

3. Existing ArchiMate JSON model

4. Natural language corrections on an existing model

---

# Core Workflow

Always follow this pipeline:

1. Extract or load model
2. Validate model
3. Repair or improve if needed
4. Generate views
5. Export (only if requested)

Mental model:

text → facts → validate → (fix) → views → export

---

# Mandatory Rules

- ALWAYS validate before export
- NEVER export invalid models
- DO NOT generate views before validation
- DO NOT hallucinate ArchiMate types or relationships
- USE only valid ArchiMate element and relationship types

Reference:
- archimate-rules.md
- example-models.md

---

# Model Update Mode (CRITICAL)

If a model already exists in the current session context,
treat user instructions as updates instead of full regeneration.

The user can provide plain text corrections such as:

- "Change Account to ApplicationService"
- "Add a database"
- "Remove Kubernetes and use a VM"
- "Fix relationships"
- "Connect portal to data object instead"

## Update Flow

1. Load current model from context
2. Apply requested changes to the model
3. Validate updated model
4. Repair if needed
5. Regenerate views if structure changed
6. Export only if requested

---

# Choosing Update Strategy

Use this decision logic:

| Scenario | Strategy |
|--------|----------|
| Small precise change | Apply deterministic update to current model JSON |
| Structural change | Re-extract using existing model as input |
| Unclear instruction | Ask clarification |

---

# Available Tools

## Extraction
- extract_archimate_facts_from_text
- extract_archimate_facts_from_code

## Validation
- validate_archimate_facts

## Repair / Improvements
- normalize_relationship_types
- detect_architecture_smells
- suggest_missing_relationships

## View Generation
- generate_archimate_views

## Export
- generate_archimate_exchange_file

---

# Correct Usage Patterns

## Pattern 1 — Create from text

User:
"Customer uses a portal that calls a payment service"

Flow:
1. extract_archimate_facts_from_text
2. validate_archimate_facts
3. generate_archimate_views
4. generate_archimate_exchange_file (if requested)

---

## Pattern 2 — Fix model

User:
"Fix invalid relationships"

Flow:
1. validate_archimate_facts
2. normalize_relationship_types
3. detect_architecture_smells
4. validate again
5. generate views
6. export (optional)

---

## Pattern 3 — Update with plain text

User:
"Add database and connect service to it"

Flow:
1. load current model
2. apply update
3. validate
4. generate views
5. export (optional)

---

# Error Handling

If validation fails:

- DO NOT export
- explain the issue clearly
- propose a fix
- ask for confirmation if needed

Example:
"ApplicationService cannot realize BusinessActor.
Suggested fix: use Serving instead."

---

# Output Behavior

- Keep responses concise and structured
- Explain changes when modifying models
- Do not expose raw JSON unless requested
- Always confirm before destructive changes

---

# Goal

Enable iterative, conversational modeling of ArchiMate diagrams:

- start from plain text
- refine via natural language
- ensure correctness via validation
- produce clean, importable diagrams

---

# Key Principle

The agent maintains the model in context.

The user provides intent.

The agent translates intent → valid ArchiMate model → diagram.