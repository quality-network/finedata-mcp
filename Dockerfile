# MCP server Dockerfile (Streamable HTTP remote mode)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY pyproject.toml README.md LICENSE ./

ENV PYTHONPATH=/app/src
ENV FINEDATA_MCP_HOST=0.0.0.0
ENV FINEDATA_MCP_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

CMD ["python", "-m", "mcp_server", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
