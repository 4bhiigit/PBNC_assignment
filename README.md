# Document Intelligence & Question Extraction Service

Asynchronous service for extracting structured questions, answer keys, and options from exam papers and question banks.

## Quick Start

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
```

Swagger UI documentation is available at `http://localhost:8000/docs`.

## Testing

```bash
pytest -v
```
