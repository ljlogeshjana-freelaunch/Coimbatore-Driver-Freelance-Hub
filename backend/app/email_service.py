from decimal import Decimal
import logging
import httpx
from .config import settings

logger = logging.getLogger(__name__)

class EmailDeliveryError(RuntimeError):
    pass

def send_email(*, to: str, subject: str, text: str) -> bool:
    """Send plain-text mail through Resend; returns false only when disabled.

    Provider errors are raised so callers can log/report delivery failure instead
    of telling an operator that an email was sent when it was not.
    """
    if not settings.resend_api_key:
        logger.info("Email not sent: RESEND_API_KEY is not configured")
        return False
    if not settings.email_from:
        raise EmailDeliveryError("EMAIL_FROM is required when Resend is enabled")
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "text": text},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("Resend delivery failed")
        raise EmailDeliveryError("Email provider rejected or failed to deliver the message") from exc
    return True

def notify_admin(subject: str, text: str) -> bool:
    return send_email(to=settings.admin_email, subject=subject, text=text)
