# CryptoAlpha

CryptoAlpha is a modular foundation for a quantitative crypto-trading platform. This initial scaffold provides service boundaries, API and WebSocket plumbing, configuration, observability hooks, and local Docker development support. Trading, strategy, portfolio, and backtesting business logic is intentionally not implemented.

## Structure

- `backend/` — FastAPI application, SQLAlchemy data layer, and domain modules.
- `frontend/` — React + TypeScript dashboard built with Vite and Tailwind CSS.

## Quick start

1. Copy `.env.example` to `.env` and review values.
2. Start the local stack: `docker compose up --build`.
3. Open the API docs at `http://localhost:8000/docs` and UI at `http://localhost:5173`.

For local backend development, create a Python virtual environment, install `backend/requirements.txt`, then run `uvicorn app.main:app --reload` from `backend/`. For the frontend, run `npm install` and `npm run dev` from `frontend/`.

## Database migrations

From `backend/`, apply the schema with `alembic upgrade head`. The initial migration creates the PostgreSQL schema and promotes `ohlcv` to a TimescaleDB hypertable when the extension is available. It remains usable as a regular indexed PostgreSQL table when TimescaleDB is not installed.

## Quality conventions

Configuration is environment-driven, request/response contracts are versioned under `app/schemas`, and domain modules own their future use cases. Keep external I/O at the API, service, database, and WebSocket boundaries.
