# --- web: build the SvelteKit PWA ---
FROM node:22 AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev
COPY frontend/ ./
RUN npm run build

# --- builder: backend venv via poetry ---
FROM python:3.12-slim AS builder
ENV POETRY_VERSION=2.1.3 POETRY_VIRTUALENVS_IN_PROJECT=true PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
WORKDIR /app/backend
COPY backend/pyproject.toml backend/poetry.lock ./
RUN poetry install --only main --no-root
COPY backend/offline_reader_api ./offline_reader_api
RUN poetry install --only main

# --- app: runtime (non-root) ---
FROM python:3.12-slim
WORKDIR /app/backend
RUN useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin appuser
COPY --from=builder --chown=appuser:appuser /app/backend /app/backend
COPY --from=web --chown=appuser:appuser /web/build /app/frontend/build
ENV PATH="/app/backend/.venv/bin:${PATH}" PYTHONUNBUFFERED=1 DATA_DIR=/data
RUN mkdir -p /data && chown appuser:appuser /data
USER appuser
EXPOSE 8000
CMD ["uvicorn", "offline_reader_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
