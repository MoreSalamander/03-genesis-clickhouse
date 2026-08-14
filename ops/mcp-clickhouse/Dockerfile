# Official ClickHouse MCP server (https://github.com/ClickHouse/mcp-clickhouse),
# installed from PyPI and run over streamable-http. Built locally so the image is
# native-arch on both dev (arm64) and Cloud Run (amd64).
FROM python:3.12-slim
RUN pip install --no-cache-dir mcp-clickhouse
EXPOSE 8000
CMD ["mcp-clickhouse"]
