# Car Crash AI

[![CI](https://github.com/Thytus777/car-crash-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Thytus777/car-crash-ai/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Thytus777/car-crash-ai/badges/coverage.json)](https://github.com/Thytus777/car-crash-ai/actions/workflows/ci.yml?query=branch%3Amain)
[![eval](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Thytus777/car-crash-ai/badges/eval.json)](https://github.com/Thytus777/car-crash-ai/actions/workflows/nightly.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

AI-powered vehicle damage detection and repair cost estimation. Upload photos of a damaged vehicle and get:

- **Vehicle identification** — make, model, year detected automatically
- **Damage assessment** — per-component severity scoring with repair/replace recommendations
- **Cost estimate** — parts pricing (live search + static fallback) and labor costs

Built with FastAPI (backend), Streamlit (frontend), and Google Gemini / OpenAI vision models.

---

## Quick Start

### Prerequisites

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)**. It installs the pinned Python (3.12, see `.python-version`) and all dependencies from `backend/uv.lock`.
- **GNU make**. On Windows: `winget install ezwinports.make`.
- **Gemini API key** (free tier available). [Get one here](https://aistudio.google.com/apikey).

### 1. Clone and install

```bash
git clone https://github.com/Thytus777/car-crash-ai.git
cd car-crash-ai
make setup        # uv sync (dev + demo groups) and install the git hooks
make help         # list every target
```

### 2. Configure API keys

```bash
cp backend/.env.example backend/.env   # Windows: copy backend\.env.example backend\.env
```

Edit `backend/.env` and add your API key:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key-here
```

> **Note:** The free Gemini tier is rate-limited. To use OpenAI instead, set `AI_PROVIDER=openai` and add your `OPENAI_API_KEY`.

### 3. Run

```bash
make run          # API on http://localhost:8000 (docs at /docs)
make run-demo     # Streamlit demo on http://localhost:8501 (second terminal)
```

> The Streamlit demo still calls endpoints that were removed. It is being fixed in [#4](https://github.com/Thytus777/car-crash-ai/issues/4).

### 4. Use it

1. Open http://localhost:8501
2. Upload 1–10 photos of a damaged vehicle
3. (Optional) Enter vehicle make/model/year in the sidebar to skip AI identification
4. Click **🔍 Analyze Damage**
5. Review the damage report and cost estimate

---

## Project Structure

```
car-crash-ai/
├── backend/
│   ├── app/
│   │   ├── api/routes/        # FastAPI endpoints (upload, analyze, estimate)
│   │   ├── core/              # Config, LLM abstraction layer
│   │   ├── data/              # Static parts pricing CSV
│   │   ├── models/            # Pydantic data models
│   │   ├── prompts/           # LLM prompt templates
│   │   ├── services/          # Business logic (vehicle ID, damage detection, cost estimation)
│   │   └── main.py            # FastAPI app entry point
│   ├── tests/                 # pytest: unit/ and integration/
│   ├── .env.example           # Environment variable template
│   ├── pyproject.toml         # Dependencies and tool config
│   └── uv.lock                # Locked dependency versions
├── frontend/
│   └── streamlit_app.py       # Streamlit UI
└── docs/
    ├── LEARNING.md             # Detailed guide to all technologies used
    ├── adr/                    # Architecture decision records
    ├── TECHSTACK.md            # Tech stack rationale
    └── PROJECT_PLAN.md         # Project plan / roadmap
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/upload` | Upload vehicle images |
| `POST` | `/api/v1/analyze` | Run full damage analysis |
| `GET` | `/api/v1/estimates` | List recent assessments |
| `GET` | `/api/v1/estimates/{id}` | Get a saved assessment |
| `GET` | `/api/v1/report/{id}` | Download the PDF report |

## Configuration

All settings are in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` | — | Gemini API key |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model name |
| `OPENAI_API_KEY` | — | OpenAI API key (when using `openai` provider) |
| `SERPAPI_KEY` | — | SerpAPI key for live price search (optional) |
| `LABOR_RATE_PER_HOUR` | `75.00` | Hourly labor rate for estimates |
| `SEVERITY_REPLACE_THRESHOLD` | `0.3` | Severity above this → replace instead of repair |

## Running Tests

```bash
make test               # unit tests: fast, no network, no real LLM
make test-integration   # FastAPI app with fixture LLM responses
make coverage           # both, with the coverage gate CI enforces
make lint typecheck     # ruff + mypy --strict
```
