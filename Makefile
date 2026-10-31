.PHONY: help install lint test snapshot pipeline dbt contracts headline rag eval dashboard benchmark tofu all

export PYTHONPATH := src

help:
	@echo "Targets: install lint test snapshot pipeline dbt contracts headline rag eval dashboard benchmark all"

install:
	python -m pip install -e ".[dev,dbt,rag,orch]"

lint:
	ruff check src tests

test:
	pytest -q

snapshot:
	python -m rba_copilot.ingest

pipeline:
	python -m rba_copilot.pipeline

dbt:
	cd transform && dbt build --profiles-dir .

contracts:
	python -m rba_copilot.contracts

headline:
	python -m rba_copilot.headline

rag:
	python -m rba_copilot.rag.index
	python -m rba_copilot.rag.answer

eval:
	python -m rba_copilot.rag.evaluate

dashboard:
	python -m rba_copilot.dashboard

benchmark:
	python -m rba_copilot.benchmark

tofu:
	cd infra/tofu && tofu init -backend=false && tofu validate

all: pipeline dbt contracts headline rag eval dashboard
