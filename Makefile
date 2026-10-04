.PHONY: dev test docker-up docker-down

dev:
	uv run uvicorn web:app --host 127.0.0.1 --port 8000 --reload

test:
	uv run pytest

docker-up:
	docker compose up --build -d --wait

docker-down:
	docker compose down
