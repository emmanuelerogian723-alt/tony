.PHONY: install run test lint fmt docker deploy

install:
	pip install -r requirements.txt

run:
	uvicorn tony.main:app --reload --port 8000

test:
	python -m pytest tests/ -q

lint:
	ruff check tony tests

fmt:
	ruff format tony tests

docker:
	docker build -t tony .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env tony

catalog:
	python scripts/generate_catalog.py
