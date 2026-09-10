# Deploy to Render (Yale Markets)

## 1. Push to GitHub

```bash
cd "C:\Users\jaden\OneDrive\Code\Yale Clubs\yale_AI\yale_kalshi"
git add -A
git status
git commit -m "Add Render deploy (gunicorn + Procfile)"
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

(Skip `git remote add` if `origin` already exists.)

## 2. Create Render Web Service

1. [https://dashboard.render.com](https://dashboard.render.com) → **New** → **Web Service**
2. Connect the GitHub repo
3. Settings:

| Field | Value |
|--------|--------|
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn -b 0.0.0.0:$PORT run:app` |

(Or leave Start Command empty if Render picks up the `Procfile`.)

## 3. Environment variables (Render → Environment)

Set **all** of these (replace placeholders):

| Key | Value |
|-----|--------|
| `FLASK_SECRET_KEY` | long random string (see generate command below) |
| `DEV_AUTH_BYPASS` | `false` |
| `CAS_USE_TEST` | `true` |
| `APP_BASE_URL` | `https://YOUR-SERVICE-NAME.onrender.com` (no trailing slash) |
| `ORIGIN` | same as `APP_BASE_URL` |
| `BOOTSTRAP_ADMIN_NETID` | your Yale NetID (lowercase, no `@yale.edu`) |
| `SEED_BALANCE` | `10000` |
| `LMSR_B` | `100` |
| `DISPUTE_HOURS` | `24` |
| `SEED_DEMO_DATA` | `true` |

Optional (email — leave blank to skip sending):

| Key | Value |
|-----|--------|
| `SMTP_HOST` | _(empty)_ |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | _(empty)_ |
| `SMTP_PASSWORD` | _(empty)_ |
| `SMTP_FROM` | `yale-markets@yale.edu` |
| `SMTP_USE_TLS` | `true` |

### Generate a secret key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 4. After first deploy

1. Open `https://YOUR-SERVICE-NAME.onrender.com`
2. Click **Sign in with CAS** — browser should go to **`secure-tst.its.yale.edu`** (not `secure.its`)
3. Confirm login lands on `/login_callback` then home

**CAS rule:** `APP_BASE_URL` must exactly match the URL you open in the browser.

## CAS: “Not Authorized to this service”

That page is Yale’s **production** CAS rejecting an unregistered app. Fix:

| Key | Value |
|-----|--------|
| `CAS_USE_TEST` | `true` |
| `APP_BASE_URL` | `https://yalshi.onrender.com` (exact URL, no trailing `/`) |
| `ORIGIN` | same as `APP_BASE_URL` |

Leave `CAS_LOGIN_URL` / `CAS_VALIDATE_URL` **unset**. Redeploy, then try again — URL bar should show `secure-tst`.

## Notes

- Free Render spins down when idle (cold start ~30s).
- SQLite lives on the instance disk and **can reset on redeploy** — fine for friend testing.
- Do **not** commit `.env` or `*.db`.
