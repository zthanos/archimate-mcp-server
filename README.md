# ArchiMate MCP Server

A deterministic ArchiMate 3.1 modeling engine with optional MCP and LLM integration for generating architecture diagrams from plain text.

## Overview

This project provides a structured, testable, and export-ready engine for creating ArchiMate models programmatically.

It supports:

- Model validation
- Automatic view generation
- Export to ArchiMate Open Exchange Format
- LLM-assisted extraction and architecture review workflows
- MCP server transport over `stdio` or `streamable-http`

## Installation

```bash
git clone https://github.com/zthanos/archimate-mcp-server
cd archimate-mcp-server
uv sync
```

## Quick Start

Run the MCP server over stdio:

```bash
uv run archimate-mcp-server
```

Export the sample model:

```bash
uv run archimate-mcp-cli export src/archimate_mcp/examples/sample_model.json --output out/model.xml
```

Run the tests:

```bash
uv run pytest -q
```

## LLM Providers

The LLM-assisted tools can run against either Anthropic or any OpenAI-compatible endpoint, including LM Studio.

### Anthropic

```bash
$env:ARCHIMATE_MCP_LLM_PROVIDER="anthropic"
$env:ARCHIMATE_MCP_LLM_MODEL="claude-opus-4-5"
$env:ARCHIMATE_MCP_LLM_API_KEY="your-key"
uv run archimate-mcp-server
```

If you want Anthropic support installed explicitly:

```bash
uv sync --extra anthropic
```

### LM Studio

1. Start LM Studio and load a model.
2. Enable the local server in LM Studio.
3. Point this project at the LM Studio OpenAI-compatible endpoint.

PowerShell example:

```powershell
$env:ARCHIMATE_MCP_LLM_PROVIDER="openai"
$env:ARCHIMATE_MCP_LLM_BASE_URL="http://127.0.0.1:1234/v1"
$env:ARCHIMATE_MCP_LLM_MODEL="local-model"
$env:ARCHIMATE_MCP_LLM_API_KEY="lm-studio"
uv run archimate-mcp-server
```

Notes:

- `ARCHIMATE_MCP_LLM_MODEL` must match the model identifier exposed by LM Studio.
- If LM Studio runs on another machine, replace `127.0.0.1` with that host.
- For Docker, use `host.docker.internal` instead of `127.0.0.1`.

## Docker

Build the image:

```bash
docker build -t archimate-mcp-server .
```

Run it as an HTTP MCP server:

```bash
docker run --rm -p 8000:8000 ^
  -e ARCHIMATE_MCP_TRANSPORT=streamable-http ^
  -e FASTMCP_HOST=0.0.0.0 ^
  -e FASTMCP_PORT=8000 ^
  archimate-mcp-server
```

The MCP endpoint will be available at:

```text
http://localhost:8000/mcp
```

### Docker with LM Studio

If LM Studio is running on your host machine:

```bash
docker compose up --build
```

The included [`compose.yaml`](/C:/Users/thano/projects/archimate-mcp-server/compose.yaml) is preconfigured to call LM Studio at:

```text
http://host.docker.internal:1234/v1
```

Update `ARCHIMATE_MCP_LLM_MODEL` in [`compose.yaml`](/C:/Users/thano/projects/archimate-mcp-server/compose.yaml) to the model name you loaded in LM Studio.

The same compose file also starts the browser-based tester at:

```text
http://localhost:8080
```

## Web Tester

You can run a local browser-based chat UI that talks to your MCP server over HTTP and follows the local ArchiMate skill workflow.

1. Start the MCP server in HTTP mode:

```powershell
$env:ARCHIMATE_MCP_TRANSPORT="streamable-http"
$env:FASTMCP_HOST="127.0.0.1"
$env:FASTMCP_PORT="8000"
uv run archimate-mcp-server
```

2. In another terminal, start the web app:

```powershell
$env:ARCHIMATE_MCP_SERVER_URL="http://127.0.0.1:8000/mcp"
uv run archimate-mcp-web
```

3. Open:

```text
http://127.0.0.1:8080
```

Notes:

- The web app reuses the local skill file at [`skills/archimate-modeler/SKILL.md`](/C:/Users/thano/projects/archimate-mcp-server/skills/archimate-modeler/SKILL.md).
- Tool execution goes through the running MCP server, not direct in-process function calls.
- Exported XML files are written under `out/web/` and exposed as download links in the chat response.
- `POST /api/chat` supports both modes:
  JSON mode with `{ "session_id": "...", "message": "...", "stream": false }`
  stream mode with `{ "session_id": "...", "message": "...", "stream": true }`, returned as `text/event-stream`

## CLI

Available commands:

- `archimate-mcp-cli validate <input>`
- `archimate-mcp-cli export <input> --output <path>`
- `archimate-mcp-cli view <input> --type application|cooperation|technology|integration`
- `archimate-mcp-cli suggest <input>`
- `archimate-mcp-cli normalize <input>`
- `archimate-mcp-cli smells <input>`

## Project Structure

```text
src/archimate_mcp/   Core engine and MCP server
skills/              Optional LLM/MCP layer assets
tests/               Test suite
```

## Testing Strategy

- Schema validation
- Relationship validation
- Layout and routing checks
- Export validation
- End-to-end workflow tests
- Provider configuration tests for LLM integration

## License

MIT License
