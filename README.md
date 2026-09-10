# Yalshi

A play-money prediction market for the Yale community. Built with Flask, SQLite, Yale CAS, LMSR trading, portfolios, leaderboards, friends, and direct messages.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Configure a local `.env` using `.env.example`. Set a strong, persistent `FLASK_SECRET_KEY` and your `BOOTSTRAP_ADMIN_NETID`. Open [localhost:5000](http://localhost:5000); `APP_BASE_URL` must match the address used for CAS.

Yale CAS is the normal sign-in method. For a local development account, explicitly set `DEV_AUTH_BYPASS=true`. Keep it false on public hosts. Shared-code preview login is opt-in via `FRIEND_ACCESS_CODE`; it does not verify Yale identity, and administrators must use CAS outside development mode.

Demo data is off by default. Existing `.env` values still override defaults.

## Verify

```powershell
.\.venv\Scripts\python.exe -B -m unittest test_regressions -v
```

Tests use isolated in-memory databases and a temporary SQLite database for concurrent requests. They do not modify the app's existing database or send real email.

See [deployment instructions](DEPLOY.md) for configuration.

Play points only. Not affiliated with Kalshi.
