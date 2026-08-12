# Genesis OS — Operational Intelligence backend (Cloud Run)
# Build from the repository root:
#   docker build -f infrastructure/cloud-run/Dockerfile -t genesis-grafana .
FROM python:3.12-slim

WORKDIR /srv
COPY pyproject.toml README.md LICENSE ./
COPY app ./app
RUN pip install --no-cache-dir .

ENV GENESIS_DATA_DIR=/tmp/genesis-data
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
