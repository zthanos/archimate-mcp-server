# ArchiMate MCP Server

A working Python MCP server that generates **ArchiMate Model Exchange XML** with simple diagram views, suitable as a starting point for import into tools such as **Archi** and **Bizzdesign Horizzon**.

The server is built on the official MCP Python SDK's `FastMCP` pattern, which exposes tools from Python functions and supports standard transports such as stdio and Streamable HTTP. citeturn740170search0turn740170search1

## What this project does

- Accepts a canonical JSON model with elements, relationships, and optional views
- Validates IDs, references, and a small legality matrix for relationships
- Generates a default diagram view when none is provided
- Exports **ArchiMate Model Exchange XML**
- Exposes the functionality through MCP tools
- Includes a CLI for local testing without an MCP client

## Current MVP scope

### Element types
- BusinessActor
- BusinessProcess
- ApplicationComponent
- ApplicationService
- DataObject
- Node
- Device
- SystemSoftware

### Relationship types
- Serving
- Access
- Assignment
- Realization
- Composition
- Aggregation
- Association
- Flow
- Triggering

## Project structure

```text
archimate-mcp-server/
├─ pyproject.toml
├─ README.md
├─ src/
│  └─ archimate_mcp/
│     ├─ __init__.py
│     ├─ builders.py
│     ├─ cli.py
│     ├─ exporter.py
│     ├─ layout.py
│     ├─ models.py
│     ├─ server.py
│     ├─ validation.py
│     └─ examples/
│        └─ sample_model.json
└─ tests/
   ├─ test_exporter.py
   └─ test_validation.py
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For tests:

```bash
pip install -e .[dev]
pytest
```

## CLI usage

Validate a model:

```bash
archimate-mcp-cli validate src/archimate_mcp/examples/sample_model.json
```

Generate XML to stdout:

```bash
archimate-mcp-cli export src/archimate_mcp/examples/sample_model.json
```

Generate XML to a file:

```bash
archimate-mcp-cli export src/archimate_mcp/examples/sample_model.json --output out/model.xml
```

## MCP usage

Start the MCP server over stdio:

```bash
archimate-mcp-server
```

Exposed tools:

- `validate_archimate_model`
- `generate_archimate_exchange_xml`
- `generate_archimate_exchange_file`

## Sample JSON input

```json
{
  "model": {
    "id": "customer-banking-model",
    "name": "Customer Banking Model"
  },
  "elements": [
    {
      "id": "app_portal",
      "type": "ApplicationComponent",
      "name": "Customer Portal"
    },
    {
      "id": "svc_accounts",
      "type": "ApplicationService",
      "name": "Accounts Service"
    },
    {
      "id": "data_account",
      "type": "DataObject",
      "name": "Account"
    }
  ],
  "relationships": [
    {
      "id": "rel_serves_1",
      "type": "Serving",
      "source": "svc_accounts",
      "target": "app_portal",
      "name": "serves"
    },
    {
      "id": "rel_access_1",
      "type": "Access",
      "source": "app_portal",
      "target": "data_account",
      "name": "reads"
    }
  ],
  "views": []
}
```

## Notes

This is an MVP, not a full implementation of every ArchiMate exchange schema feature. The exporter is intentionally compact and deterministic so you can extend it with:

- XSD validation
- organizations/folders
- property definitions
- more complete legality rules
- richer layout strategies
- import/merge support

## Why this project shape

The official MCP docs recommend building servers with `FastMCP`, using Python functions as tools with schemas generated from type hints and docstrings. citeturn740170search0turn740170search1
