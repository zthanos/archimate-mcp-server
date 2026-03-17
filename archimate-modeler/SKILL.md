---
name: archimate-modeler
description: >
  Create ArchiMate 3.1 architecture diagrams from free text, code summaries, or
  existing architecture descriptions. Use this skill whenever the user wants to:
  - Generate an ArchiMate diagram or model from a text description
  - Convert a system description, README, or architecture doc into ArchiMate
  - Export an ArchiMate model as an importable .xml file for Archi or other tools
  - Validate, repair, or extend an existing ArchiMate JSON model
  - Correct, update, or patch a model already generated in the current session
  - Suggest missing relationships or detect architecture smells in a model
  Always use this skill when the user mentions ArchiMate, architecture diagrams,
  Archi tool, EA modelling, or asks to "model", "diagram", or "fix" a system
  architecture — even if they phrase it conversationally.
compatibility:
  tools:
    - archimate-mcp (MCP server — required for all operations)
---

# ArchiMate Modeler

Generate, validate, export, and iteratively improve ArchiMate 3.1 architecture
diagrams from natural language or code summaries, using the archimate-mcp MCP
server tools.

---

## Core Mental Model

```
text → facts → validate → (fix) → views → export
```

**Rule: no validation → no export.** Always validate before calling
`generate_archimate_exchange_file`.

---

## Entry Points

There are three ways a session can start:

| Situation | Entry point |
|---|---|
| User describes a system in plain text | Step 1 — Extract from text |
| User provides code / README / service list | Step 1 — Extract from code |
| User pastes or references an existing model JSON | Step 2 — Validate directly |
| Model already exists in context + user requests a correction | Update mode |

---

## Step 1 — Extract Facts

Choose tool based on input type:

| Input | Tool |
|---|---|
| Free text description | `extract_archimate_facts_from_text` |
| Code / README / service list / dependency graph | `extract_archimate_facts_from_code_summary` |

Pass `existing_model_json` if merging into an existing model.

After extraction, show the user a compact summary — not raw JSON:
```
Extracted: N elements, M relationships
Elements: [type: name, ...]
Warnings: [any validation_warnings if present]

Να συνεχίσω με validation;
```

---

## Step 2 — Validate

Call `validate_archimate_facts` with the model JSON.

- **Valid** → proceed
- **Errors** → explain in plain language, suggest fixes:
  - Unknown element types → suggest correct ArchiMate type
  - Illegal relationships → explain the rule and suggest the correct direction/type
  - Missing elements → ask if they should be added

See `references/archimate-rules.md` for valid types and allowed combinations.

---

## Step 3 — Repair (Optional but Recommended)

Offer repairs when the model seems incomplete or has quality issues.
Present one at a time — don't overwhelm the user.

**Suggest missing relationships**
```
Call: suggest_missing_relationships(model_json)
Show: source → [type] → target | rationale
Ask:  "Θες να προσθέσω κάποιο;"
```

**Normalize relationship types**
```
Call: normalize_relationship_types(model_json)
Show: rel_id: current → suggested | rationale
Ask:  "Να εφαρμόσω τις διορθώσεις;"
```

**Detect architecture smells**
```
Call: detect_architecture_smells(model_json)
Show: [severity] description → suggested fix
```
Block export on `error`-severity smells unless user explicitly overrides.

---

## Step 4 — Generate Views

Call `generate_archimate_views` before export if the model has no views,
or if the structure changed since last generation.

---

## Step 5 — Export

Call `generate_archimate_exchange_file`:
- `model_json`: final validated model JSON
- `output_path`: suggest `out/<model-id>.xml`

On success, tell the user:
```
✔ Export completed
Path: out/<filename>.xml
Views: N (<view names>)

Import στο Archi:
File → Import → Open Exchange File Format
```

---

## Update Mode (Corrections on Existing Model)

If a model has already been generated in the current session, the user may
request corrections in plain text. Treat this as a patch to the current model
in context — not a full regeneration.

**Typical update requests:**
- "Άλλαξε το Account σε ApplicationService"
- "Πρόσθεσε database"
- "Αφαίρεσε το Kubernetes και βάλε VM"
- "Σύνδεσε το portal με το DataObject αντί για το service"
- "Διόρθωσε τα invalid relationships"
- "Μετονόμασε το Customer Portal σε Web Portal"

**When to patch vs re-extract:**

| Request type | Approach |
|---|---|
| Precise change (rename, add/remove element, fix type) | Patch JSON directly |
| Broad enrichment ("κάν' το πιο complete", "πρόσθεσε technology layer") | Re-extract with `existing_model_json` |

**Update flow:**
1. Apply changes to current model JSON in context
2. `validate_archimate_facts` on the updated model
3. `generate_archimate_views` if structure changed
4. Export only if requested

Do not ask the user to re-paste the full JSON — use the model already in context.

---

## Interaction Guidelines

**Be concise in confirmations.** Show summary tables, not raw JSON.
Only show full JSON if the user explicitly asks.

**One question at a time.** Don't present all repair options at once.
Sequence: validate → smells → missing rels → export.

**Handle ambiguity gracefully.** Make a reasonable type choice and explain it.
The user can correct iteratively.

**Cross-layer patterns to watch for:**
- `BusinessActor` → Assignment → `BusinessProcess`
- `ApplicationComponent` → Realization → `ApplicationService`
- `ApplicationService` → Serving → `ApplicationComponent` or `BusinessProcess`
- `Node` → Composition → `ApplicationComponent` (deployment)

---

## Example Flows

### A — From plain text

```
User: Ένας Customer χρησιμοποιεί ένα Customer Portal που καλεί
      ένα Account Service που τρέχει σε Kubernetes.

→ extract_archimate_facts_from_text
→ show summary, ask to continue
→ validate_archimate_facts
→ suggest_missing_relationships (optional)
→ generate_archimate_views
→ generate_archimate_exchange_file
```

### B — Fix existing model

```
User: [pastes JSON] Αυτό έχει λάθη.

→ validate_archimate_facts   ← mandatory first
→ explain errors
→ normalize_relationship_types
→ detect_architecture_smells
→ generate_archimate_views
→ generate_archimate_exchange_file
```

### C — Direct export

```
User: Κάνε export αυτό το model σε Archi XML.

→ validate_archimate_facts   ← mandatory
→ generate_archimate_views   ← if no views
→ generate_archimate_exchange_file
```

### D — Iterative correction (VS Code / agent context)

```
User: Άλλαξε το Account σε ApplicationService και πρόσθεσε component.

→ patch current model JSON in context
→ validate_archimate_facts
→ generate_archimate_views
→ (export if requested)
```

---

## Reference Files

- `references/archimate-rules.md` — Valid element types, relationship types,
  and allowed (source, type, target) combinations. Read when validation fails
  or when helping fix illegal relationships.

- `references/example-models.md` — Canonical JSON examples for common patterns
  (3-tier web app, microservices, event-driven). Read when the user asks to
  model a known pattern or needs a starting point.