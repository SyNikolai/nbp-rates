.DEFAULT_GOAL := help
.PHONY: help ingest backfill transform check test lint format clean

FROM ?= 2020-01-01
RUN := uv run python -m nbp_pipeline.cli

help: ## Possible targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf " \033[36m%-10s\033[0m %s\n", $$1, $$2}'

ingest: ## Fetching new rates since last watermark
	$(RUN) ingest

backfill: ## Fetch history since FROM (default 01-01-2020)
	$(RUN) backfill --from $(FROM)

transform: ## Build the parquet staging and DuckDB warehouse
	$(RUN) transform

check: ## Data quality check
	$(RUN) check

test: ## Unit tests
	uv run pytest -q

lint: ## Liniting and formatticng check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto fix lint and format issues
	uv run ruff check --fix .
	uv run ruff format .

clean: ## Delete staging and warehouse
	rm -rf dta/staging data/warehouse.duckdb
