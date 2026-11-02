# VoiceDocs Backend

FastAPI backend for VoiceDocs.

## Stack

- Python 3.11+
- FastAPI
- PostgreSQL
- SQLAlchemy 2
- Alembic (migrations are introduced in the next database phase)
- Pydantic Settings

## 1. Clone and switch to the feature branch

```bash
git clone https://github.com/Onkar2104/logsbee-VoiceDocs-Backend.git
cd logsbee-VoiceDocs-Backend
git checkout feature/phase-1-foundation
```

## 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies and configure environment

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy the example environment file:

Windows PowerShell:
```powershell
Copy-Item .env.example .env
```

macOS/Linux:
```bash
cp .env.example .env
```

Update `DATABASE_URL` in `.env` with your local PostgreSQL credentials. Create a PostgreSQL database named `voicedocs` first.

## 4. Run the API

```bash
uvicorn main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health
- Database readiness: http://127.0.0.1:8000/api/v1/health/ready

The readiness endpoint returns HTTP 503 until PostgreSQL is reachable.

## Architecture direction

VoiceDocs will validate the signed-in user through the Logsbee User Management API. VoiceDocs will store its own domain data and external Logsbee user/account UUID references; it will not duplicate Logsbee's users, roles, or permissions tables.
