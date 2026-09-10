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

A shared access code enables unverified NetID access for non-admin accounts. Anyone with that code can claim another non-admin NetID. Use only with disposable preview data and trusted testers. Administrator accounts require CAS unless development bypass is explicitly enabled.

## Email

Leave `SMTP_HOST` empty to disable delivery. Otherwise configure `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (default yalshi@yale.edu), and `SMTP_USE_TLS` (default true). Use a sender your mail provider authorizes.

Email currently runs synchronously during resolution. For larger deployments, move delivery to a durable queue after database commit.

## Verify after deployment

1. Confirm the home page and assets load with Yalshi branding.
2. Sign in through CAS and confirm the return destination.
3. Confirm public users cannot access admin actions.
4. Exercise market creation, approval, a play-point trade, and portfolio updates with test accounts.
5. Verify sign-out remains effective on the next request.

Run `python -B -m unittest test_regressions -v` before deployment. Keep `.env` and databases out of Git. No deployment or remote account changes were made as part of this audit.
