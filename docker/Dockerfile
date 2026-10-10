FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY app ./app
COPY agent ./agent

RUN pip install --upgrade pip && pip install --no-cache-dir -e .

RUN addgroup --system chargepilot && adduser --system --ingroup chargepilot chargepilot \
    && chown -R chargepilot:chargepilot /app

USER chargepilot

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
