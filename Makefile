.PHONY: setup dev down logs test lint migrate

setup:
	python -m venv .venv
	.venv/Scripts/python -m pip install -e "./apps/api[dev]"
	npm install

dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	.venv/Scripts/python -m pytest apps/api/tests
	npm run typecheck:web

lint:
	.venv/Scripts/python -m ruff check apps/api/src apps/api/tests
	npm run lint:web

migrate:
	.venv/Scripts/python -m alembic -c apps/api/alembic.ini upgrade head

