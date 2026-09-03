.PHONY: install backend frontend test verify corpus
PYTHON ?= python
NPM ?= npm

install:
	$(PYTHON) -m pip install -r backend/requirements-test.txt
	cd frontend && $(NPM) ci

backend:
	$(PYTHON) -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && $(NPM) run dev

test:
	$(PYTHON) -m pytest
	cd frontend && $(NPM) test

verify:
	$(PYTHON) -m ruff check backend src scripts tests
	$(PYTHON) -m ruff format --check backend src scripts tests
	$(PYTHON) -m pytest
	cd frontend && $(NPM) run typecheck && $(NPM) run lint && $(NPM) run format:check && $(NPM) test && $(NPM) run build

corpus:
	$(PYTHON) -m scripts.fetch_legal_corpus
