.PHONY: help install lint test snapshot pipeline dbt rag eval dashboard all

help:
	@echo "Targets: install lint test snapshot pipeline dbt rag eval dashboard all"

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check src tests

test:
	pytest -q

snapshot:
	python -m rba_copilot.ingest

pipeline:
	python -m rba_copilot.pipeline

dbt:
	cd transform && dbt build

rag:
	python -m rba_copilot.rag.build

eval:
	python -m rba_copilot.rag.evaluate

dashboard:
	python -m rba_copilot.dashboard

all: pipeline dbt rag eval dashboard
