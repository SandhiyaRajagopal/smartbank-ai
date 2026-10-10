# ---------- Stage 1: build the React frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python runtime (FastAPI serves API + built UI) ----------
FROM python:3.12-slim
# TZ: the simulated bank and its customers are in India - fraud rules like "unusual hour"
# must use IST, not the container's default UTC. (POSIX form: works without tzdata.)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=IST-5:30
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ backend/
COPY docs/ docs/
COPY --from=frontend /app/frontend/dist frontend/dist

# run as a non-root user; /app/data holds the SQLite DBs and the vector index
RUN useradd --create-home appuser && mkdir -p data && chown appuser data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health')"
# Cloud Run injects $PORT (8080); locally it defaults to 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
