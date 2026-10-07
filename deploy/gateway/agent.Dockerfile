FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.11
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY data/canonical/interview-wwi-v1 ./data/canonical/interview-wwi-v1
COPY reports/interview-wwi-v1/identity_map.csv ./reports/interview-wwi-v1/identity_map.csv
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "export OPERION_OBSERVED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ); exec operion-agent"]
