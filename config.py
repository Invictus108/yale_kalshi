import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    MAX_CONTENT_LENGTH = 1024 * 1024
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'yale_markets.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Yale_Books: ORIGIN + "/login_callback"
    ORIGIN = os.getenv("ORIGIN", os.getenv("APP_BASE_URL", "http://localhost:5000")).rstrip(
        "/"
    )
    APP_BASE_URL = os.getenv("APP_BASE_URL", ORIGIN).rstrip("/")

    # Hardcoded Yale_Books test CAS URLs (do not point these at secure.its without ITS).
    CAS_LOGIN_URL = os.getenv(
        "CAS_LOGIN_URL", "https://secure-tst.its.yale.edu/cas/login"
    )
    CAS_VALIDATE_URL = os.getenv(
        "CAS_VALIDATE_URL",
        "https://secure-tst.its.yale.edu/cas/p3/serviceValidate",
    )

    # Preview login is explicitly opt-in. Public hosting never enables it.
    FRIEND_ACCESS_CODE = os.getenv("FRIEND_ACCESS_CODE", "").strip()
    DEV_AUTH_BYPASS = os.getenv("DEV_AUTH_BYPASS", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    # Shared-code access is for private previews, not verified Yale identity.
    ENABLE_NETID_LOGIN = DEV_AUTH_BYPASS or bool(FRIEND_ACCESS_CODE)

    BOOTSTRAP_ADMIN_NETID = os.getenv("BOOTSTRAP_ADMIN_NETID", "admin").lower()
    SEED_BALANCE = float(os.getenv("SEED_BALANCE", "10000"))
    LMSR_B = float(os.getenv("LMSR_B", "100"))
    DISPUTE_HOURS = int(os.getenv("DISPUTE_HOURS", "24"))
    SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "false").lower() in {
        "1",
        "true",
        "yes",
    }

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "yalshi@yale.edu")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
