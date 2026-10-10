FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

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
