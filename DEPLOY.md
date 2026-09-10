# Deploy Yalshi

## Application commands

Build: `pip install -r requirements.txt`

Start on a Linux host: `gunicorn -b 0.0.0.0:$PORT run:app`

Use the repository's Procfile or configure the start command directly. With no `DATABASE_URL`, SQLite uses `yale_markets.db` in the repository directory. For durable deploys, set `DATABASE_URL` to a persistent SQLite path or a Postgres URL and arrange backups.

## Configuration

| Variable | Setting |
| --- | --- |
| FLASK_SECRET_KEY | Strong, persistent random secret, identical across workers |
| DATABASE_URL | Optional SQLAlchemy URL; unset uses local `yale_markets.db` |
| APP_BASE_URL | Public HTTPS origin, without a trailing slash |
| ORIGIN | Same origin as APP_BASE_URL |
| BOOTSTRAP_ADMIN_NETID | Administrator's Yale NetID |
| DEV_AUTH_BYPASS | false on public hosts |
| FRIEND_ACCESS_CODE | Empty for CAS-only access; nonempty only for a private preview |
| SEED_DEMO_DATA | false |
| SEED_BALANCE | 10000 |
| LMSR_B | 100 (must be positive) |
| DISPUTE_HOURS | 24 |
| CAS_LOGIN_URL | CAS login endpoint approved for this deployment |
| CAS_VALIDATE_URL | Corresponding CAS serviceValidate endpoint |

The code defaults to Yale test CAS endpoints. Register the exact callback `{APP_BASE_URL}/login_callback` with the identity provider as required. Public deployment does not automatically enable NetID login. The old `CAS_USE_TEST` variable is not used; configure the endpoint URLs directly.

A missing `FLASK_SECRET_KEY` generates a temporary process-local secret. This is suitable only for disposable development: restarts invalidate sessions, and separate workers may disagree. Always configure a persistent key for deployment.

## Preview access

A shared access code enables unverified NetID access (including admin / bootstrap NetIDs) until production CAS is allowlisted. Anyone with the code can claim any NetID. Use only with trusted testers.

## Email

Leave `SMTP_HOST` empty to disable delivery. Otherwise configure `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (default yalshi@yale.edu), and `SMTP_USE_TLS` (default true). Use a sender your mail provider authorizes.

Email currently runs synchronously during resolution. For larger deployments, move delivery to a durable queue after database commit.

## Settlement without page visits

The application processes expired markets and due undisputed proposals during relevant page requests. There is no built-in background timer. Run this command in the application environment to process them explicitly:

```bash
python -m flask --app run:app settle-markets
```

For unattended operation, configure your host's scheduler to run it periodically with the same DATABASE_URL and application configuration as the web service. Do not point a scheduler at a separate ephemeral SQLite copy. Disputed markets remain for admin review; repeating the command does not pay a settled market twice.

Purchases stop at closes_at. Cash-out remains available for existing holdings until settlement; due undisputed proposals settle before further trading is accepted. Admin settlement can end the dispute window early.

## Database behavior and verification limits

SQLite mutation requests acquire a write lock before balances and quantities are read. PostgreSQL trades lock the market row, and ledger updates lock the account row. Keep transactions short and monitor lock timeouts under load. The regression suite verifies SQLite concurrency; PostgreSQL concurrency still needs integration testing against your deployment database.

The app creates missing tables at startup; it does not migrate existing schemas or copy data when DATABASE_URL changes. Back up the database before deployment. Demo mode is optional and should remain disabled with real data.

Charts load a pinned Chart.js script from jsDelivr. If it fails, the page shows a chart-unavailable message while balances and holdings remain readable.

## Verify after deployment

1. Confirm the home page and assets load with Yalshi branding.
2. Sign in through CAS and confirm the return destination.
3. Confirm public users cannot access admin actions.
4. Exercise market creation, approval, a play-point trade, and portfolio updates with test accounts. Confirm cash-out works after purchases close, updates the balance, and cannot be repeated on sold shares.
5. Verify sign-out remains effective on the next request.

6. Check that a due undisputed proposal settles once through the lifecycle command and that disputed markets remain pending admin action.

Run `python -B -m unittest test_regressions -v` before deployment (28 tests in the current suite). Keep `.env`, databases, and internal reports out of Git. This polish pass did not deploy the app or change remote accounts.
