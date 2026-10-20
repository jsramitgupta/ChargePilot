FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHARGEPILOT_CONNECTOR_CONFIG=/data/connector-config.json

WORKDIR /opt/chargepilot

COPY connector/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt \
    && pip install --no-cache-dir --root-user-action=ignore --upgrade setuptools==84.2.0 \
    && groupadd --system --gid 10001 chargepilot \
    && useradd --uid 10001 --gid chargepilot --home-dir /home/chargepilot chargepilot \
    && mkdir -p /data \
    && chown chargepilot:chargepilot /data

COPY connector/__init__.py ./connector/__init__.py
COPY connector/chargepilot_connector.py ./connector/chargepilot_connector.py

USER 10001:10001

CMD ["python", "-m", "connector.chargepilot_connector"]
