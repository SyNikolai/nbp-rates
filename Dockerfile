FROM python:3.12-slim

# Same uv version as local development (check with: uv --version)
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first: this layer stays cached until uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the code, which changes far more often
COPY . .
RUN uv sync --frozen --no-dev

# Don't run as root
RUN useradd --create-home app && chown -R app /app
USER app

CMD ["sh", "-c", "python -m nbp_pipeline.cli ingest && python -m nbp_pipeline.cli transform && python -m nbp_pipeline.cli check"]
