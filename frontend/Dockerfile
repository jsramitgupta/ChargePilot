FROM node:24-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS frontend-build

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade setuptools==84.2.0 msgpack==1.2.3 urllib3==2.8.0 \
    && groupadd --system --gid 10001 chargepilot \
    && useradd --system --uid 10001 --gid chargepilot --create-home --home-dir /home/chargepilot chargepilot

COPY app/frontend_server.py ./app/frontend_server.py
COPY --from=frontend-build /build/dist ./frontend-dist

USER 10001:10001

EXPOSE 5173

CMD ["python", "app/frontend_server.py"]
