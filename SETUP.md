# Setup Guide

Manual setup steps required for each feature. Updated as new features are added.

---

## Prerequisites (One-Time Setup)

### 1. Python Environment
```bash
# Install Python 3.11+ from https://www.python.org/downloads/
python --version  # Should show 3.11+

# Create a virtual environment
cd backend
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate (macOS/Linux)
source venv/bin/activate
```

### 2. API Keys
Create a `.env` file in `backend/` (this file is git-ignored):
```env
# Required — Vision LLM for vehicle ID + damage detection + price extraction
OPENAI_API_KEY=sk-your-key-here

# Required — Web search for live part prices (get free key at https://serpapi.com)
SERPAPI_KEY=your-serpapi-key-here

# Optional — Override defaults
# LABOR_RATE_PER_HOUR=75.00
# PRICE_CACHE_TTL_HOURS=24
```

### 3. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 4. Database (Phase 2+)
PostgreSQL is not needed for the MVP. The MVP uses in-memory data and CSV files.
When ready:
```bash
# Install PostgreSQL 15+ from https://www.postgresql.org/download/
# Create database
createdb car_crash_ai
# Set in .env
# DATABASE_URL=postgresql://user:password@localhost:5432/car_crash_ai
```

---

## Per-Feature Setup

> Each feature section below is added when the feature is developed.
> Check this file after pulling new feature branches.

### Feature: Project Scaffolding (`feature/project-scaffolding`)

**Branch:** `feature/project-scaffolding`

**Setup steps:**
```bash
# 1. Create and activate virtual environment
cd backend
python -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# macOS/Linux
# source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install dev/test dependencies
pip install pytest pytest-asyncio

# 4. Copy .env.example to .env and fill in your API keys
copy .env.example .env
# Then edit .env with your actual keys

# 5. Verify everything works
python -m pytest tests/test_health.py -v

# 6. Run the server
uvicorn app.main:app --reload
# API docs at http://localhost:8000/docs
```

**What was created:**
- FastAPI app skeleton with health check endpoint
- API route stubs: `/api/v1/upload`, `/api/v1/analyze`, `/api/v1/estimate/{id}`
- Pydantic models: `Vehicle`, `DamageItem`, `DamageAssessment`, `PriceResult`, `CostEstimate`, `AssessmentReport`
- LLM prompt templates: vehicle identification, damage assessment, price extraction
- Service stubs: image processing, vehicle ID, damage detection, cost estimation
- Configuration via `pydantic-settings` with `.env` support
- Test scaffold with async client fixture

### Feature: Streamlit Frontend (`feature/frontend-streamlit`)

**Setup steps:**
```bash
# 1. Ensure backend deps are up to date (streamlit added)
cd backend
pip install -r requirements.txt

# 2. Start the backend API (Terminal 1)
uvicorn app.main:app --reload

# 3. Start the Streamlit frontend (Terminal 2)
cd frontend
streamlit run streamlit_app.py
# Opens at http://localhost:8501
```

**⚠️ Manual setup required:**
- You need your `OPENAI_API_KEY` set in `backend/.env` for the AI analysis to work
- You need your `SERPAPI_KEY` set in `backend/.env` for live price search (optional — falls back to static CSV)

**What was created:**
- Streamlit app with image upload, optional vehicle info override
- Damage report with severity bars and repair/replace recommendations
- Cost estimate breakdown with parts, labor, and grand total
- Raw JSON report view
