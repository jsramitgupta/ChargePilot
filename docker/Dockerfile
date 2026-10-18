FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 chargepilot \
    && useradd --system --uid 10001 --gid chargepilot --create-home --home-dir /home/chargepilot chargepilot

COPY pyproject.toml README.md ./
COPY app ./app
COPY agent ./agent
COPY connector ./connector

RUN pip install --no-cache-dir .

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
