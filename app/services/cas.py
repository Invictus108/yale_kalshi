"""Yale CAS helpers — mirrors Yale_Books backend/app.py flow."""

from __future__ import annotations

import requests
import xmltodict
from flask import current_app


def cas_login_url() -> str:
    return current_app.config["CAS_LOGIN_URL"]


def cas_validate_url() -> str:
    return current_app.config["CAS_VALIDATE_URL"]


def service_url() -> str:
    """Must match exactly what was sent to CAS as service= (login_callback)."""
    return current_app.config["APP_BASE_URL"].rstrip("/") + "/login_callback"


def parse_cas_response(xml_text: str) -> dict:
    return xmltodict.parse(xml_text, dict_constructor=dict)


def validate_ticket(ticket: str) -> str:
    """
    Validate a CAS service ticket and return NetID.
    Same approach as Yale_Books: GET p3/serviceValidate + xmltodict.
    """
    params = {
        "ticket": ticket,
        "service": service_url(),
    }
    resp = requests.get(cas_validate_url(), params=params, timeout=20)
    resp.raise_for_status()
    data = parse_cas_response(resp.text)

    sr = data.get("cas:serviceResponse", {})

    if "cas:authenticationFailure" in sr or "authenticationFailure" in sr:
        failure = sr.get("cas:authenticationFailure") or sr.get("authenticationFailure") or {}
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
