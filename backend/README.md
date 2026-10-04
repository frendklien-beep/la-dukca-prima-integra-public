# Backend

This directory contains a sanitized portfolio-safe subset of the La Dukca PRIMA Integra FastAPI backend.

## Scope

The code illustrates:

- application factory and API routing;
- configuration via environment variables;
- SQLAlchemy and Alembic persistence patterns;
- conversation orchestration;
- retrieval and grounding components;
- privacy and safety checks;
- deterministic fallback behavior;
- representative automated tests.

The public snapshot intentionally excludes production data, production environment files, internal acceptance datasets, operational evidence, deployment automation, and the private admin/authentication control plane. The runnable public API surface is limited to system endpoints and citizen-facing chat.

## Requirements

- Python 3.14
- pip
- a local SQLite database for development

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
```

The example environment file contains placeholders only. If you want to exercise model-backed generation locally, set your own development API key in the untracked `.env` file.

## Run

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Tests

```powershell
pytest
```

The included tests are representative rather than the complete internal QA suite.

## Important Boundary

This backend tree is a portfolio snapshot. It is not connected to production deployment and is not the operational source of truth.
