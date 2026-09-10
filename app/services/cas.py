"""Yale CAS helpers — mirrors Yale_Books backend/app.py exactly."""

from __future__ import annotations

import os

import requests
import xmltodict
from flask import current_app

# Hardcoded like Yale_Books (test CAS). Prod requires ITS service registration.
CAS_LOGIN_URL = "https://secure-tst.its.yale.edu/cas/login"
CAS_VALIDATE_URL = "https://secure-tst.its.yale.edu/cas/p3/serviceValidate"


def cas_login_url() -> str:
    # Allow env override only if explicitly set; default = Yale_Books test CAS.
    return current_app.config.get("CAS_LOGIN_URL") or CAS_LOGIN_URL


def cas_validate_url() -> str:
    return current_app.config.get("CAS_VALIDATE_URL") or CAS_VALIDATE_URL


def service_url() -> str:
    """
    Same as Yale_Books:
      SERVICE_URL = os.getenv("ORIGIN", "http://localhost:5000") + "/login_callback"
    We also honor APP_BASE_URL (alias for ORIGIN).
    """
    origin = (
        current_app.config.get("APP_BASE_URL")
        or current_app.config.get("ORIGIN")
        or os.getenv("ORIGIN")
        or "http://localhost:5000"
    ).rstrip("/")
    return origin + "/login_callback"


def parse_cas_response(xml_text: str) -> dict:
    return xmltodict.parse(xml_text, dict_constructor=dict)


def validate_ticket(ticket: str) -> str:
    """Validate CAS ticket → NetID (Yale_Books flow)."""
    params = {
        "ticket": ticket,
        "service": service_url(),
    }
    resp = requests.get(cas_validate_url(), params=params, timeout=20)
    resp.raise_for_status()
    data = parse_cas_response(resp.text)

    sr = data.get("cas:serviceResponse") or data.get("serviceResponse") or {}

    # Yale_Books checks key without cas: prefix after xmltodict; handle both.
    failure = sr.get("cas:authenticationFailure") or sr.get("authenticationFailure")
    if failure:
        if isinstance(failure, dict):
            reason = failure.get("@code", failure.get("#text", "UNKNOWN"))
        else:
            reason = str(failure)
        raise RuntimeError(f"CAS Authentication failed: {reason}")

    success = sr.get("cas:authenticationSuccess") or sr.get("authenticationSuccess")
    if not success:
        raise RuntimeError("CAS returned no authenticationSuccess node")

    netid = success.get("cas:user") or success.get("user")
    if isinstance(netid, dict):
        netid = netid.get("#text")
    if not netid:
        raise RuntimeError("CAS success response missing user/NetID")
    return str(netid).strip().lower()


def cas_public_status() -> dict:
    """Safe debug payload (no secrets)."""
    return {
        "cas_login_url": cas_login_url(),
        "cas_validate_url": cas_validate_url(),
        "service_url": service_url(),
        "note": (
            "Yale test CAS allows http://localhost:5000/login_callback "
            "(Yale_Books). Public Render URLs return "
            "'Not Authorized to this service' until ITS allowlists them."
        ),
    }
