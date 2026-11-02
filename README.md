# VoiceDocs Backend

FastAPI backend for VoiceDocs.

## Stack

- Python 3.11+
- FastAPI
- PostgreSQL
- SQLAlchemy 2
- Alembic
- Pydantic Settings
- HTTPX for the Logsbee User Management API

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

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Update `DATABASE_URL` with your local PostgreSQL credentials. Create a PostgreSQL database named `voicedocs` first.

Set `LOGSBEE_USER_API_BASE_URL` to the URL where your Logsbee User Management API is running. The example uses port 8001 so VoiceDocs can run on port 8000 locally.

## 4. Run VoiceDocs

```bash
uvicorn main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health
- Database readiness: http://127.0.0.1:8000/api/v1/health/ready
- Authenticated user: http://127.0.0.1:8000/api/v1/me

## Logsbee authentication

VoiceDocs does not issue or validate its own login tokens. Send the Logsbee-issued access token to VoiceDocs as a Bearer token. VoiceDocs forwards it to Logsbee's authenticated `GET /api/users/me` endpoint and returns the validated user/account/role/permission/product context.

The Logsbee endpoint is being added separately in [logsbee-user PR #4](https://github.com/Onkar2104/logsbee-user/pull/4). That PR must be merged/deployed before the VoiceDocs `/api/v1/me` endpoint can be tested end-to-end.

VoiceDocs stores its own domain data and external Logsbee user/account UUID references; it does not duplicate Logsbee's users, roles, or permissions tables.


## Phase 2: Documents and access control

Run the initial schema migration after configuring PostgreSQL:

```powershell
alembic upgrade head
```

### Document endpoints

All endpoints below require the Logsbee-issued Bearer access token.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/documents/` | Create a document |
| GET | `/api/v1/documents/` | List documents visible to the caller |
| GET | `/api/v1/documents/{document_id}` | Read a document |
| PUT | `/api/v1/documents/{document_id}` | Update a document |
| DELETE | `/api/v1/documents/{document_id}` | Soft-delete a document |
| POST | `/api/v1/documents/{document_id}/shares` | Share with a same-account user |
| GET | `/api/v1/documents/{document_id}/shares` | List shares (owner/Admin only) |
| DELETE | `/api/v1/documents/{document_id}/shares/{user_id}` | Revoke sharing |
| POST | `/api/v1/documents/{document_id}/edit-requests` | Request edit access |
| PATCH | `/api/v1/documents/{document_id}/edit-requests/{user_id}` | Approve/reject a pending request |

### Access rules

- The document owner and the Logsbee Account Admin for that account can view, edit, delete, share, revoke shares, and review edit requests.
- A shared user can view the document and request edit access.
- A shared user can edit only after the owner or Account Admin approves the request.
- Shared users cannot delete, share, revoke shares, or approve requests.
- Share recipients are checked by Logsbee using the caller's Bearer token and must be active users in the same account.
- Documents are soft-deleted; deleted documents are excluded from normal reads and lists.
- VoiceDocs does not create or duplicate Logsbee users, accounts, roles, or permissions.

The Logsbee membership verification route is provided by [logsbee-user PR #4](https://github.com/Onkar2104/logsbee-user/pull/4). Run Logsbee on the URL configured by `LOGSBEE_USER_API_BASE_URL`.
