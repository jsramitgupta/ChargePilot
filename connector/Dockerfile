FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHARGEPILOT_CONNECTOR_CONFIG=/data/connector-config.json

WORKDIR /opt/chargepilot

COPY connector/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system --gid 10001 chargepilot \
    && useradd --system --uid 10001 --gid chargepilot --home-dir /home/chargepilot chargepilot \
    && mkdir -p /data \
    && chown chargepilot:chargepilot /data

COPY connector/__init__.py ./connector/__init__.py
COPY connector/chargepilot_connector.py ./connector/chargepilot_connector.py

USER 10001:10001

CMD ["python", "-m", "connector.chargepilot_connector"]
