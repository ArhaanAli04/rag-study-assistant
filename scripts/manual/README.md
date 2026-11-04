# Manual scripts (not tests)

These were `src/test_*.py`. They call live services (Gemini, Tavily, Redis) and mostly print
results instead of asserting, so pytest must never collect them: `pytest.ini` limits collection to
`tests/` (T1, Day 5). The offline test suite lives in `tests/`.

Run one by hand from the repo root, with the root `.env` filled in and Redis running:

```powershell
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
python scripts/manual/test_chunking.py
```

Some of them resolve sample files relative to the old `src/` location and may need a path
adjusted before they run. Eval scripts among them are rewritten on Days 11–12; the rest are
reviewed in the Day 10 cleanup.
