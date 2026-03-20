FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARCHIMATE_MCP_TRANSPORT=streamable-http \
    FASTMCP_HOST=0.0.0.0 \
    FASTMCP_PORT=8000

WORKDIR /app

COPY pyproject.toml README.md main.py /app/
COPY src /app/src

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["archimate-mcp-server"]
