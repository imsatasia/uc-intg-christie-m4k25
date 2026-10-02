# External-driver deployment: run as a Docker container on the LAN, joined
# into this homelab's compose.yaml like every other service. See
# references/packaging-and-deployment.md for the on-remote sandboxed
# alternative (PyInstaller --onedir + .tar.gz archive), which this Dockerfile
# does not build.
FROM python:3.11-slim-bookworm

WORKDIR /app

# Official static uv binary -- see
# https://docs.astral.sh/uv/guides/integration/docker/ -- rather than
# `pip install uv`, so the installer itself isn't a moving dependency.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
COPY driver.json driver.json
COPY uc_intg_christie_m4k25 uc_intg_christie_m4k25

# --frozen: fail the build rather than silently re-resolve if uv.lock is out
# of sync with pyproject.toml. --no-dev: skip pytest/black/isort/pylint/
# flake8, none of which the running driver needs.
RUN uv sync --frozen --no-dev
RUN mkdir /config

ENV PATH="/app/.venv/bin:$PATH"

# UC_INTEGRATION_HTTP_PORT is the WebSocket server's listen port despite the
# name. UC_CONFIG_HOME must point at a writable, persisted volume -- see
# docker-compose.yml.
ENV UC_CONFIG_HOME="/config"
ENV UC_INTEGRATION_INTERFACE="0.0.0.0"
ENV UC_INTEGRATION_HTTP_PORT="9090"
ENV UC_DISABLE_MDNS_PUBLISH="false"

CMD ["python3", "-u", "-m", "uc_intg_christie_m4k25"]
