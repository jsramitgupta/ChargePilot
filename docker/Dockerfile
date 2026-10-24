FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce AS build

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

RUN python -m venv /opt/venv \
    && python -c 'import tomllib; from pathlib import Path; project = tomllib.loads(Path("pyproject.toml").read_text()); dependencies = project["project"]["dependencies"] + project["build-system"]["requires"]; Path("/tmp/chargepilot-build-requirements.txt").write_text("\n".join(dependencies) + "\n", encoding="utf-8")' \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/chargepilot-build-requirements.txt

COPY app ./app
COPY connector ./connector

RUN /opt/venv/bin/pip install --no-cache-dir --no-deps --no-build-isolation . \
    && /opt/venv/bin/pip uninstall --yes setuptools wheel

FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system --gid 10001 chargepilot \
    && useradd --uid 10001 --gid chargepilot --create-home --home-dir /home/chargepilot chargepilot

COPY --from=build /opt/venv /opt/venv
COPY app ./app
COPY connector ./connector

RUN /opt/venv/bin/python -m pip uninstall --yes pip setuptools \
    && /usr/local/bin/python -m pip uninstall --yes pip setuptools \
    && rm -rf /usr/local/lib/python3.15/ensurepip

FROM scratch AS final

COPY --from=runtime / /

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
