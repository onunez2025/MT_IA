# SOLE AI Backend - Fase 0

Conversational AI backend for SOLE AI - Sales data query system powered by FastAPI, Azure SQL, and Deepseek API.

## Setup

### 1. Create virtual environment

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 2. Create `.env` from `.env.example`

```bash
cp .env.example .env
```

Then fill in your credentials:
- Entra ID credentials for authentication
- SQL Server connection details (read-only users only)
- SAP API credentials
- Deepseek API key

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python main.py
```

The API will be available at `http://127.0.0.1:8000`

### 5. Verify health endpoint

```bash
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{"status": "ok", "version": "0.1.0"}
```

## Documentation

- **FastAPI Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Testing

Run all tests with coverage:

```bash
pytest tests/ -v --cov=.
```

Run specific test file:

```bash
pytest tests/test_connectors.py -v
```

## Architecture

- **Capa 3 Gateway:** RBAC validation and audit logging
- **Capa 4 Orchestrator:** Tool selection and routing
- **Capa 5 AI Engine:** Deepseek API integration

## Environment Variables

See `.env.example` for all available configuration options.

Key variables:
- `ENVIRONMENT`: `development` or `production`
- `DEBUG`: `True` or `False`
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `DEEPSEEK_API_KEY`: Deepseek API key for AI responses

## Security

- All database queries are read-only (INSERT/UPDATE/DELETE blocked)
- RBAC validation against Microsoft Entra ID
- Immutable audit logging for all queries
- Token consumption tracking

## License

Internal use only - MT INDUSTRIAL S.A.C
