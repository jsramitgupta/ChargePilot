FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHARGEPILOT_CONNECTOR_CONFIG=/data/connector-config.json

WORKDIR /opt/chargepilot

COPY connector/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt \
    && python -m pip uninstall --yes pip setuptools \
    && rm -rf /usr/local/lib/python3.15/ensurepip \
    && groupadd --system --gid 10001 chargepilot \
    && useradd --uid 10001 --gid chargepilot --home-dir /home/chargepilot chargepilot \
    && mkdir -p /data \
    && chown chargepilot:chargepilot /data

COPY connector/__init__.py ./connector/__init__.py
COPY connector/chargepilot_connector.py ./connector/chargepilot_connector.py

FROM scratch AS final

COPY --from=runtime / /

WORKDIR /opt/chargepilot

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHARGEPILOT_CONNECTOR_CONFIG=/data/connector-config.json \
    PATH="/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"

USER 10001:10001

CMD ["python", "-m", "connector.chargepilot_connector"]
