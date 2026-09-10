import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _cas_hosts(use_test: bool) -> tuple[str, str]:
    # CRITICAL: production CAS (secure.its) requires ITS service registration.
    # Student demos must use secure-tst (same as Yale_Books) or you get
    # "You are Not Authorized to this service."
    host = "https://secure-tst.its.yale.edu/cas" if use_test else "https://secure.its.yale.edu/cas"
    return f"{host}/login", f"{host}/p3/serviceValidate"


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'yale_markets.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEV_AUTH_BYPASS = os.getenv("DEV_AUTH_BYPASS", "false").lower() in {
        "1",
        "true",
        "yes",
    }

    # Same shape as Yale_Books: ORIGIN/APP_BASE_URL + /login_callback
    # Yale_Books defaults to http://localhost:5000
    APP_BASE_URL = os.getenv(
        "APP_BASE_URL",
        os.getenv("ORIGIN", "http://localhost:5000"),
    ).rstrip("/")

    CAS_USE_TEST = os.getenv("CAS_USE_TEST", "true").lower() in {"1", "true", "yes"}
    _login, _validate = _cas_hosts(CAS_USE_TEST)
    CAS_LOGIN_URL = os.getenv("CAS_LOGIN_URL", _login)
    CAS_VALIDATE_URL = os.getenv("CAS_VALIDATE_URL", _validate)

    BOOTSTRAP_ADMIN_NETID = os.getenv("BOOTSTRAP_ADMIN_NETID", "admin").lower()
    SEED_BALANCE = float(os.getenv("SEED_BALANCE", "10000"))
    LMSR_B = float(os.getenv("LMSR_B", "100"))
    DISPUTE_HOURS = int(os.getenv("DISPUTE_HOURS", "24"))
    SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() in {
        "1",
        "true",
        "yes",
    }

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "yale-markets@yale.edu")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
