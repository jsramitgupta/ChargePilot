FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /app

RUN groupadd --system --gid 10001 chargepilot \
    && useradd --system --uid 10001 --gid chargepilot --create-home --home-dir /home/chargepilot chargepilot

COPY app/frontend_server.py ./app/frontend_server.py
COPY --from=frontend-build /build/dist ./frontend-dist

USER 10001:10001

EXPOSE 5173

CMD ["python", "app/frontend_server.py"]
