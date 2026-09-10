# Yale Markets — Play-money campus prediction market

Flask + SQLite. Yale CAS (same pattern as Yale_Books), LMSR trading, friends/DMs, popular feed.

## Quick start

```bash
cd yale_kalshi
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open **http://localhost:5000** (not `127.0.0.1` — must match `APP_BASE_URL`) and click **Sign in with CAS**.

### CAS (mirrors Yale_Books)

| Step | URL |
|------|-----|
| Start login | `/login` → Yale CAS |
| Callback | `/login_callback?ticket=…` |
| Validate | `…/cas/p3/serviceValidate` |

Defaults:
- Test CAS: `https://secure-tst.its.yale.edu/cas` (`CAS_USE_TEST=true`)
- Service: `http://localhost:5000/login_callback`

Production: set `CAS_USE_TEST=false` (uses `secure.its.yale.edu`).

### Local NetID bypass

`DEV_AUTH_BYPASS=true` → http://localhost:5000/dev-login

See `HANDOFF.md` for architecture.

## Disclaimer

Play money only. Not affiliated with Kalshi.
