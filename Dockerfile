FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_PATH=/mcp
ENV P0_ARTIFACT_DIR=/tmp/chatgpt-web-hwpx-mcp-p0

EXPOSE 8000

CMD ["python", "server.py"]
