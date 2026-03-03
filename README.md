# Car Crash AI

AI-powered vehicle damage detection and repair cost estimation. Upload photos of a damaged vehicle and get:

- **Vehicle identification** — make, model, year detected automatically
- **Damage assessment** — per-component severity scoring with repair/replace recommendations
- **Cost estimate** — parts pricing (live search + static fallback) and labor costs

Built with FastAPI (backend), Streamlit (frontend), and Google Gemini / OpenAI vision models.

---

## Quick Start

### Prerequisites

- **Python 3.11+** — [Download](https://www.python.org/downloads/)
- **Gemini API key** (free) — [Get one here](https://aistudio.google.com/apikey)

### 1. Clone the repo

```bash
git clone https://github.com/thytus777/car-crash-ai.git
cd car-crash-ai
```

### 2. Set up the backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# macOS/Linux
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure API keys

```bash
# Copy the example env file
# Windows
copy .env.example .env
# macOS/Linux
# cp .env.example .env
```

Edit `backend/.env` and add your API key:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key-here
```

> **Note:** The free Gemini tier has rate limits (500 requests/day for gemini-2.5-flash). For production, set `AI_PROVIDER=openai` and add your `OPENAI_API_KEY`.

### 4. Start the backend (Terminal 1)

```bash
cd backend
.\venv\Scripts\Activate.ps1    # Windows
# source venv/bin/activate     # macOS/Linux

uvicorn app.main:app --reload
```

The API runs at **http://localhost:8000** — interactive docs at http://localhost:8000/docs

### 5. Start the frontend (Terminal 2)

```bash
cd backend
.\venv\Scripts\Activate.ps1    # Windows
# source venv/bin/activate     # macOS/Linux

cd ../frontend
streamlit run streamlit_app.py
```

The UI opens at **http://localhost:8501**

### 6. Use it

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
│   ├── tests/                 # pytest test suite
│   ├── .env.example           # Environment variable template
│   └── requirements.txt       # Python dependencies
├── frontend/
│   └── streamlit_app.py       # Streamlit UI
├── LEARNING.md                # Detailed guide to all technologies used
└── SETUP.md                   # Per-feature setup instructions
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/upload` | Upload vehicle images |
| `POST` | `/api/v1/analyze` | Run full damage analysis |
| `GET` | `/api/v1/estimate/{id}` | Get cost estimate by ID |

## Configuration

All settings are in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` | — | Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `OPENAI_API_KEY` | — | OpenAI API key (when using `openai` provider) |
| `SERPAPI_KEY` | — | SerpAPI key for live price search (optional) |
| `LABOR_RATE_PER_HOUR` | `75.00` | Hourly labor rate for estimates |
| `SEVERITY_REPLACE_THRESHOLD` | `0.3` | Severity above this → replace instead of repair |

## Running Tests

```bash
cd backend
.\venv\Scripts\Activate.ps1    # Windows
# source venv/bin/activate     # macOS/Linux

python -m pytest tests/ -v
```
