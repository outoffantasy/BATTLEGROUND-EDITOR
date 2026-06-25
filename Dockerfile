# syntax=docker/dockerfile:1

FROM node:22-trixie AS node

FROM python:3.12-trixie

ENV VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/opt/venv/bin:/usr/local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && pip install --no-cache-dir uv==0.11.16

WORKDIR /workspace/backend

COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./

RUN uv sync --frozen --all-groups \
    && python -m playwright install --with-deps chromium

WORKDIR /workspace

CMD ["bash"]
