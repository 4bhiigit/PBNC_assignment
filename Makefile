.PHONY: up down migrate test lint demo samples openapi clean

up:
	docker compose up --build -d

down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

test:
	pytest -v

lint:
	ruff check app tests scripts
	ruff format --check app tests scripts
	mypy app

demo:
	python scripts/run_demo.py

samples:
	python scripts/generate_samples.py

openapi:
	python scripts/export_openapi.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .coverage htmlcov
