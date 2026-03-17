# 🧠 ArchiMate MCP Server

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)]()
[![Status](https://img.shields.io/badge/status-active-success.svg)]()

An MCP (Model Context Protocol) server that enables AI agents to **create, update, validate, repair, and export ArchiMate models** from plain text.

> Turn natural language into **valid ArchiMate diagrams** — iteratively.

---

# ⚡ 30-Second Quick Start

```bash
git clone https://github.com/zthanos/archimate-mcp-server
cd archimate-mcp-server
uv sync
uv run server.py
```

Then describe your architecture:

```text
Customer uses a portal that calls an account service
```

👉 The agent will generate a valid ArchiMate model, validate it, and prepare it for export.

---

# 🚀 What This Solves

Creating ArchiMate diagrams manually is:

* slow
* error-prone
* hard to maintain

This project enables:

✅ **Conversational modeling**
✅ **Validation-first architecture design**
✅ **Agent-driven diagram generation**

---

# ✨ Features

* 🧠 Plain text → ArchiMate model
* 🔁 Iterative updates via natural language
* ✅ Validation against ArchiMate rules
* 🛠 Automatic repair & improvement suggestions
* 📊 View generation (diagram-ready)
* 📦 Export to Archi Open Exchange Format (XML)
* 🤖 Designed for AI agents (VS Code / Copilot / MCP)

---

# ⚡ Quick Example

### Input

```text
Customer uses a portal that calls an account service
```

### Output

* Valid ArchiMate model
* Relationships validated
* Diagram views generated
* Exportable XML for Archi

---

### Then refine it:

```text
Add a database
Change Account to ApplicationService
Remove Kubernetes and use a VM
```

➡️ The model is updated — no need to recreate anything.

---

# 🧠 Core Workflow

```text
text → facts → validate → (fix) → views → export
```

### Key Rule

> ❗ No validation → No export

---

# 🧩 MCP Integration

This server is built for **agentic workflows**.

The agent:

* maintains the model in context
* applies updates from user intent
* ensures correctness before export

👉 Perfect for:

* VS Code agents
* Copilot extensions
* custom LLM pipelines

---

# 📦 Installation

```bash
git clone https://github.com/zthanos/archimate-mcp-server
cd archimate-mcp-server

uv sync
```

---

# ▶️ Run Server

```bash
uv run server.py
```

---

# 🧪 CLI Usage

```bash
uv run archimate-mcp-cli export \
  src/archimate_mcp/examples/sample_model.json \
  --output out/model.xml
```

---

# 🛠 Available Tools

## Extraction

* `extract_archimate_facts_from_text`
* `extract_archimate_facts_from_code_summary`

## Validation

* `validate_archimate_facts`

## Repair / Improvement

* `normalize_relationship_types`
* `detect_architecture_smells`
* `suggest_missing_relationships`

## Views

* `generate_archimate_views`

## Export

* `generate_archimate_exchange_file`

---

# 🔁 Example Workflow

## 1. Create

```text
Customer uses a portal that calls a payment service
```

## 2. Update

```text
Add database and connect service to it
```

## 3. Export

```text
Export this model
```

---

# ⚠️ Rules & Constraints

* Models must follow ArchiMate specification
* Invalid relationships are rejected
* Export is blocked if validation fails
* Views generated only after validation

---

# 📁 Project Structure

```text
src/
  archimate_mcp/
    server.py
    cli.py
    exporter.py
    layout.py
    validation.py
    examples/

SKILL.md
archimate-rules.md
example-models.md
```

```

---

# 🧪 Example Output

✔ Archi-compatible XML  
✔ Import directly into Archi:

```

File → Import → Open Exchange Format

```

---

# 🎯 Design Principles

### 1. Agent-first
Built for LLM agents, not manual editing.

### 2. Iterative modeling
The model evolves through conversation.

### 3. Validation-first
Invalid architecture is blocked early.

### 4. Deterministic output
Stable, tool-compatible results.

---

# 🚧 Roadmap

- [ ] Persistent model storage
- [ ] Multi-view generation (Application / Technology / Business)
- [ ] Smarter layout (edge routing improvements)
- [ ] Live diagram preview (SVG)
- [ ] Round-trip editing with Archi

---

# 🤝 Contributing

Contributions welcome.

Focus areas:
- extraction accuracy
- validation rules
- layout improvements
- MCP integrations

---

# 📚 References

- ArchiMate Specification (The Open Group)
- Archi Tool: https://www.archimatetool.com/
- Archi Import/Export Plugins:
  https://github.com/archimatetool/archi/wiki/Developing-Import-and-Export-Plug-ins

---

# 📄 License

MIT License

```
