---
name: running-tests
description: "Runs and manages pytest test suites. Use when asked to run tests, debug test failures, or check test coverage."
---

# Testing for Car Crash AI

## Running Tests

### Full test suite
```bash
cd backend
python -m pytest tests/ -v
```

### Specific test file
```bash
python -m pytest tests/test_upload.py -v
```

### With coverage
```bash
python -m pytest tests/ --cov=app --cov-report=term-missing
```

### Async tests
All async tests use `pytest-asyncio`. Ensure `pytest.ini` or `pyproject.toml` has:
```ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Writing Tests

### API endpoint tests
```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_upload_image():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with open("tests/fixtures/sample_damage.jpg", "rb") as f:
            response = await client.post("/api/v1/upload", files={"images": f})
        assert response.status_code == 200
```

### Service tests
```python
from app.services.damage_detect import assess_damage

@pytest.mark.asyncio
async def test_severity_in_range():
    result = await assess_damage(image_paths=["tests/fixtures/sample_damage.jpg"])
    for damage in result.damages:
        assert 0.0 <= damage.severity <= 1.0
```

## Test Structure
- `tests/fixtures/` — sample images and test data
- `tests/conftest.py` — shared fixtures (test client, mock LLM responses)
- Test file naming mirrors source: `app/services/cost_estimate.py` → `tests/test_cost_estimate.py`

## Debugging Failures
1. Run the failing test in isolation with `-v --tb=long`
2. Check if it's an async issue (missing `@pytest.mark.asyncio`)
3. Check if LLM calls are properly mocked (tests should never call real APIs)
4. Check fixture data exists in `tests/fixtures/`
