# HANDOFF LOG — Yale Markets (play-money)

Living handoff for other agents/humans. Append new entries at the bottom when you change behavior.

## Product decisions (locked)

| Decision | Choice | Why |
|----------|--------|-----|
| Stack | Python Flask + SQLite + Jinja | Requested by user |
| Trading | **LMSR AMM** (`b=100` default) | Better than CLOB for thin campus markets; continuous prices; no need for matching makers |
| Auth | Yale CAS (**Yale_Books pattern**: `/login` → `/login_callback` + `p3/serviceValidate`) + optional `/dev-login` | Copied from working Yale_Books repo |
| Market create | Any user → status `pending` → admin approve → `open` | Requested |
| Anonymity | NetID private; public `display_name` + `is_anonymous_display` | Requested |
| Admin | Bootstrap NetID from env; admins can promote/demote others | Requested |
| Chat | Per-market chat + **friend DMs** | Requested |
| Social | People search, profiles, friend requests, earnings | Requested |
| Feed | Popularity-ranked markets + friend chips | Requested |
| Email | On propose / dispute / resolve for holders+creator | Skips send if `SMTP_HOST` empty; still logs to `notification_logs` |
| Currency rail | Ledger `rail='PLAY'` only | Upgrade path: add Kalshi rail later, never convert PLAY→USD in-app |

## Resolution policy (implemented)

1. Creator must write **resolution_criteria** + **resolution_source** at create time.
2. After `closes_at`, market auto-flips `open`→`closed` on view/trade attempts.
3. **Creator or admin** proposes YES/NO + evidence → status `proposed`, dispute window `DISPUTE_HOURS` (24).
4. Any logged-in user can **dispute** during the window → `disputed`.
5. **Admin finalizes** YES / NO / VOID → settle ledger + email.
6. **VOID** pays 0.5 pts per share held (neutral unwind). YES pays 1.0 per YES share; NO pays 1.0 per NO share.

### Recommended ops rules (not coded as hard law)

- Reject markets with vague criteria (“Will the vibe be good?”).
- Prefer public sources (YDN, athletics, Yale websites) over DMs/private knowledge.
- Ban markets on graded coursework outcomes / private student data.
- If evidence is ambiguous after dispute, prefer VOID over forcing an outcome.

## Repo map

```
yale_kalshi/
  HANDOFF.md              ← this file
  README.md
  requirements.txt
  config.py               ← env-driven settings
  run.py                  ← entrypoint
  .env / .env.example
  yale_markets.db         ← created at runtime (gitignored)
  app/
    __init__.py           ← create_app, db.create_all, bootstrap admin
    extensions.py         ← db, login_manager
    models.py             ← User, Market, Ledger*, Position, Trade, Chat, Friendship, DirectMessage, NotificationLog
    blueprints/
      auth.py             ← Yale_Books-style CAS (/login, /login_callback), /dev-login, settings
      main.py             ← popular feed, portfolio, leaderboard
      markets.py          ← CRUD-ish, trade, market chat, propose/dispute/finalize
      social.py           ← people search, profiles, friends, DM chat
      admin.py            ← approve/reject, finalize queue, promote admin
    services/
      cas.py              ← ticket validate (requests + xmltodict), service URL
      amm.py              ← LMSR math
      ledger.py           ← append-only style entries + balance
      trading.py          ← execute_trade, settle_market
      resolve.py          ← propose/dispute/finalize workflow
      email_notify.py     ← SMTP + NotificationLog
      users.py            ← get_or_create_user, portfolio_value, anon names
      friends.py          ← friend graph + DMs
      feed.py             ← popular feed + user_stats/earnings
    templates/ ...
    static/css/style.css
```

## Env knobs

- `DEV_AUTH_BYPASS=false` → real CAS at `/login` (Yale_Books-style).
- `DEV_AUTH_BYPASS=true` → also enables `/dev-login`.
- `APP_BASE_URL` / `ORIGIN` → must be the browser origin; callback is `{APP_BASE_URL}/login_callback`.
- `CAS_USE_TEST=true` → `secure-tst.its.yale.edu` (Yale_Books default); `false` → prod `secure.its.yale.edu`.
- `BOOTSTRAP_ADMIN_NETID`, `SEED_BALANCE`, `LMSR_B`, `DISPUTE_HOURS`, `SMTP_*` as before.

## How to run

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

- **CAS:** open http://127.0.0.1:5000/login → Yale CAS.
- **Local without CAS:** set `DEV_AUTH_BYPASS=true`, use `/dev-login` as NetID `admin`.

### Yale CAS checklist

1. `DEV_AUTH_BYPASS=false`
2. `CAS_USE_REQUEST_HOST=true` (or set `APP_BASE_URL` to the exact public URL)
3. Service URL must be stable: `{base}/login` with **no** `ticket`/`next` query params (next is stored in session)
4. If ticket validation fails off-campus, register the service URL with Yale ITS / ask for CAS client allowlisting
5. Prefer HTTPS public URL for anything beyond laptop demos

## Process log (build + debug)

### 2026-09-09 — Initial build

1. Confirmed empty repo; chose LMSR over CLOB for campus liquidity.
2. Scaffolded Flask app factory, SQLAlchemy models, blueprints, Jinja UI.
3. Implemented CAS via `python-cas` with explicit DEV bypass for local.
4. Wired ledger + LMSR trade path + settlement.
5. Wired approval queue, propose/dispute/finalize, per-market chat, leaderboard, settings (anon + email opt-in), admin promote.
6. `pip install -r requirements.txt` in `.venv` (Python 3.11.7) — success.
7. **Smoke test** (`app.test_client` + in-process trading):
   - Bootstrap admin balance 10000
   - BUY 10 YES cost ≈ 5.12, price 0.5 → ~0.525
   - Propose + finalize YES → trader balance ≈ 10004.88 (paid ~5.12, received 10)
   - HTTP `/`, `/login`, `/admin/`, `/leaderboard` → 200
8. **Bug found & fixed:** `finalize_resolution` called `settle_market` before collecting holders, so resolution emails would only hit the creator. Fixed by snapshotting holder IDs before settle.
9. **SQLite datetime:** switched `utcnow()` to naive `datetime.utcnow()` to avoid aware/naive compare errors.
10. Removed unused `flask_login` import alias in `app/__init__.py`.

### 2026-09-09 — CAS Not Authorized root cause

Live probe: Yalshi correctly uses secure-tst + `https://yalshi.onrender.com/login_callback`.
Yale test CAS still 403s that service URL. localhost works (Yale_Books). Render URLs do not.
Added FRIEND_ACCESS_CODE NetID login + `/cas-debug`; CAS code aligned to Yale_Books hardcoding.


1. Added `gunicorn` to `requirements.txt` and `Procfile`.
2. Added `DEPLOY.md` with Render build/start commands + env var table.


Project files moved from `yale_AI/yale_kalshi/` up to `yale_AI/` so the GitHub repo root is the app (not a nested folder). Agent workspace root updated accordingly.


1. `services/history.py` builds cash balance series from ledger entries.
2. Portfolio page charts it with Chart.js.
3. `SEED_DEMO_DATA=true` seeds Maya / AnonPuffin / Rio as friends of bootstrap admin with sample DMs, plus backdated ledger history for the admin chart.


1. Replaced cream/terracotta look with Yale blue + cool stone (`Instrument Serif` + `DM Sans`).
2. Logged-out full-bleed hero; logged-in compact feed header.
3. Market feed as interactive rows (hover lift, staggered fade-in); YES/NO soft chips.
4. Mobile nav toggle; polished trade/profile/people/admin templates.
5. Motion: heroIn, rise; respects `prefers-reduced-motion`.

### 2026-09-09 — Align CAS with Yale_Books

1. Read working CAS in `Yale_Books/backend/app.py`.
2. Replaced `python-cas` with the same manual flow:
   - `CAS_LOGIN_URL` + `CAS_VALIDATE_URL` (`secure-tst` by default)
   - Fixed `SERVICE_URL = APP_BASE_URL + /login_callback`
   - `/login` only redirects to CAS
   - `/login_callback` validates ticket via `p3/serviceValidate` + `xmltodict`
3. Added `app/services/cas.py`; deps `requests`, `xmltodict`.
4. Default `APP_BASE_URL=http://localhost:5000` (same as Yale_Books `ORIGIN`).
5. `CAS_USE_TEST=true` → `secure-tst.its.yale.edu`; set `false` for prod `secure.its.yale.edu`.
6. Logout matches Yale_Books (local session clear only).


### Known limitations / next agent todos

- [ ] `datetime-local` close times treated as naive wall clock (not real TZ conversion). Improve with explicit timezone.
- [ ] No CSRF tokens yet — add Flask-WTF before public deploy.
- [ ] Chat is full-page POST refresh; could add polling/SSE.
- [ ] No rate limits / chat moderation tools beyond admin social process.
- [ ] LMSR sell path can error if extreme; add clearer UX quotes (“this trade costs X”).
- [ ] Pre-trade cost preview endpoint would help UX.
- [ ] If Yale rejects unregistered `http://127.0.0.1:5000/login`, deploy to HTTPS hostname and register with ITS.
- [ ] Dual-rail Kalshi adapter not started (by design for Phase 3).
- [ ] Tests are manual smoke script only — add `pytest` suite.
- [ ] `notify_market_holders` still used for propose/dispute; after resolve uses explicit holder snapshot (good). Consider unifying.
- [ ] Friend notifications (email on request) not implemented yet.

## Smoke script (re-runnable)

From repo root with venv active:

```bash
python -c "from app import create_app; app=create_app(); c=app.test_client(); print(c.get('/').status_code)"
```

Full trading smoke was run once during initial build (see process log). Re-running creates additional DB rows in `yale_markets.db`; delete the DB file to reset.

## Agent instructions for continuing

1. Read this file + `README.md` + `config.py` first.
2. Prefer extending `services/` rather than putting business logic in blueprints.
3. Keep PLAY ledger rail separate from any future real-money adapter.
4. Append a dated Process log section for every non-trivial change + bugs fixed.
5. Do not commit `.env` or `*.db`.
