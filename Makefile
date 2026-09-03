.PHONY: install run index docker-up
install:
	python -m pip install -e .
run:
	streamlit run app.py
index:
	python scripts/index_documents.py data/documents
docker-up:
	docker compose up --build
