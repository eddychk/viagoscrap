from __future__ import annotations

import os
import smtplib
from typing import Any
from email.mime.text import MIMEText

import httpx


RESEND_API_URL = "https://api.resend.com/emails"


def _default_provider() -> str:
    return os.getenv("EMAIL_PROVIDER", "resend").strip().lower()


def send_min_drop_email(
    *,
    event_name: str,
    event_url: str,
    old_price: float,
    new_price: float,
    currency: str = "EUR",
    recipients: list[str] | None = None,
) -> dict[str, Any]:
    to_list = [mail.strip().lower() for mail in (recipients or []) if mail and mail.strip()]
    default_to = os.getenv("ALERT_TO_EMAIL")
    if default_to:
        to_list.append(default_to.strip().lower())
    to_list = sorted(set(to_list))
    if not to_list:
        return {"sent": False, "reason": "no_recipients"}

    provider = _default_provider()
    if provider == "smtp":
        return _send_via_smtp(
            event_name=event_name,
            event_url=event_url,
            old_price=old_price,
            new_price=new_price,
            currency=currency,
            recipients=to_list,
        )
    return _send_via_resend(
        event_name=event_name,
        event_url=event_url,
        old_price=old_price,
        new_price=new_price,
        currency=currency,
        recipients=to_list,
    )


def _build_email_content(event_name: str, event_url: str, old_price: float, new_price: float, currency: str) -> tuple[str, str]:
    subject = f"[ViagoScrap] Nouveau prix minimum: {new_price:.2f} {currency}"
    dashboard_url = os.getenv("DASHBOARD_URL", "http://127.0.0.1:8000")
    html = f"""
    <h2>Nouveau prix minimum detecte</h2>
    <p><strong>Event:</strong> {event_name}</p>
    <p><strong>Ancien min:</strong> {old_price:.2f} {currency}</p>
    <p><strong>Nouveau min:</strong> {new_price:.2f} {currency}</p>
    <p><a href="{event_url}">Voir la page Viagogo</a></p>
    <p><a href="{dashboard_url}">Ouvrir le dashboard</a></p>
    """
    return subject, html


def _send_via_resend(
    *,
    event_name: str,
    event_url: str,
    old_price: float,
    new_price: float,
    currency: str,
    recipients: list[str],
) -> dict[str, Any]:
    api_key = os.getenv("RESEND_API_KEY", "")
    sender = os.getenv("ALERT_FROM_EMAIL", "")
    if not (api_key and sender):
        return {"sent": False, "reason": "resend_not_configured"}
    subject, html = _build_email_content(event_name, event_url, old_price, new_price, currency)

    with httpx.Client(timeout=15.0) as client:
        response = client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": sender, "to": recipients, "subject": subject, "html": html},
        )

    if response.status_code >= 400:
        return {"sent": False, "reason": "provider_error", "status_code": response.status_code, "body": response.text}

    return {"sent": True, "provider": "resend", "recipients": recipients}


def _send_via_smtp(
    *,
    event_name: str,
    event_url: str,
    old_price: float,
    new_price: float,
    currency: str,
    recipients: list[str],
) -> dict[str, Any]:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("ALERT_FROM_EMAIL", "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "y"}
    if not (host and username and password and sender):
        return {"sent": False, "reason": "smtp_not_configured"}

    subject, html = _build_email_content(event_name, event_url, old_price, new_price, currency)
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(host, port, timeout=20) as server:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.sendmail(sender, recipients, msg.as_string())
    return {"sent": True, "provider": "smtp", "recipients": recipients}
