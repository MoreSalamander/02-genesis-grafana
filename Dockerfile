# Genesis OS — Operational Intelligence backend (Cloud Run)
# Lives at the repo root so `gcloud run deploy --source .` finds it.
#   docker build -t genesis-grafana .
FROM python:3.12-slim

WORKDIR /srv
COPY pyproject.toml README.md LICENSE ./
COPY app ./app
RUN pip install --no-cache-dir .

# The studio's record travels with the deployment: the data dir (episodic,
# events, cognition, plays) plus the PG snapshot from ops/export_snapshot.py.
COPY data ./data
ENV GENESIS_DATA_DIR=/srv/data
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
