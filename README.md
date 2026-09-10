# Yale Markets — Play-money campus prediction market

Flask + SQLite. Yale CAS (same pattern as Yale_Books), LMSR trading, friends/DMs, popular feed.

## Quick start (local)

```bash
cd yale_kalshi
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open **http://localhost:5000** (must match `APP_BASE_URL`) → **Sign in with CAS**.

## Deploy (Render)

See **[DEPLOY.md](DEPLOY.md)** for build/start commands and the full env-var list.

Short version:

- Build: `pip install -r requirements.txt`
- Start: `gunicorn -b 0.0.0.0:$PORT run:app`
- Set `APP_BASE_URL` to your `https://….onrender.com` URL

## CAS

Defaults use Yale test CAS (`secure-tst`), same as Yale_Books.  
Callback: `{APP_BASE_URL}/login_callback`

## Disclaimer

Play money only. Not affiliated with Kalshi.
