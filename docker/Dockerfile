FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci

COPY frontend ./frontend
COPY app/static ./app/static
RUN npm --prefix frontend run build

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 chargepilot \
    && useradd --system --uid 10001 --gid chargepilot --create-home --home-dir /home/chargepilot chargepilot

COPY pyproject.toml README.md ./
COPY app ./app
COPY agent ./agent
COPY connector ./connector
COPY docker/entrypoint.py ./docker/entrypoint.py
COPY --from=frontend-build /build/frontend/dist ./frontend-dist

RUN pip install --no-cache-dir .

USER 10001:10001

EXPOSE 8000 5173

CMD ["python", "docker/entrypoint.py"]
