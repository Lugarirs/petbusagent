# PetBus 🐾
Pet-friendly bus booking MVP: pet seats (first come, first served), vaccination document check, drop-point selection, operator dashboard.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload          # API on :8000 (docs at /docs)
streamlit run frontend/app.py              # UI on :8501
```

## AI agent (Google ADK)
Get a key at aistudio.google.com, then `export GOOGLE_API_KEY=...` before starting uvicorn. Without it the rest of the app still works.

## Upgrading from the first version
Delete `petbus.db` once (new columns and tables), then restart the API.

## Deploy (Render)
Push to GitHub, then Render > New > Blueprint > pick the repo (uses render.yaml).
Note: SQLite resets on Render free tier; switch to Postgres before real use.

## Roadmap
1. Pet profile + owner reviews
2. Postgres + Alembic
3. Razorpay test-mode payments
4. Operator login, multi-route, waitlist
