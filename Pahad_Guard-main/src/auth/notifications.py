"""Send login/signup notification emails via the Brevo (Sendinblue) API.

Brevo's transactional email endpoint is used directly over HTTPS, so the
only extra dependency needed is `requests`, which this project already has.

Two kinds of emails are sent on every login/signup:
  1. A confirmation email to the user themselves (their own email address).
  2. An admin alert to NOTIFY_EMAIL (the site owner), if configured.

Docs: https://developers.brevo.com/reference/sendtransacemail
"""

import os
from datetime import datetime, timezone
from typing import Optional

import requests

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _api_key_configured() -> tuple[bool, Optional[str]]:
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key or api_key == "your-brevo-api-key":
        return False, "BREVO_API_KEY is not configured in your .env file."
    return True, None


def _sender() -> tuple[str, str]:
    sender_email = os.getenv("BREVO_SENDER_EMAIL") or os.getenv("NOTIFY_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Pahad Guard")
    return sender_email, sender_name


def _send_email(to_email: str, subject: str, html_content: str) -> tuple[bool, str]:
    configured, reason = _api_key_configured()
    if not configured:
        return False, reason

    sender_email, sender_name = _sender()
    if not sender_email or sender_email == "you@example.com":
        return False, "BREVO_SENDER_EMAIL (or NOTIFY_EMAIL) is not configured in your .env file."

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }
    headers = {
        "accept": "application/json",
        "api-key": os.getenv("BREVO_API_KEY"),
        "content-type": "application/json",
    }

    try:
        response = requests.post(BREVO_ENDPOINT, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            return True, "Email sent."
        return False, f"Brevo API error ({response.status_code}): {response.text}"
    except requests.RequestException as error:
        return False, f"Could not reach Brevo API: {error}"


def send_user_notification(event: str, full_name: str, email: str) -> tuple[bool, str]:
    """Email the user themselves to confirm their signup/login.

    `event` should be "signup" or "login". Sent automatically to whichever
    email address the user just signed up / logged in with — no extra setup
    beyond BREVO_API_KEY and a verified Brevo sender is required.
    Never raises — returns (False, reason) on any failure so it never blocks
    the auth flow.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if event == "signup":
        subject = "Welcome to Pahad Guard — account created"
        heading = "Your account has been created 🎉"
        body_line = "Thanks for signing up! Your account is ready to use."
    else:
        subject = "Pahad Guard — new login to your account"
        heading = "New login to your account"
        body_line = (
            "We noticed a new login to your Pahad Guard account. "
            "If this wasn't you, please secure your account."
        )

    html_content = f"""
        <html>
          <body>
            <h2>{heading}</h2>
            <p>Hi {full_name or email},</p>
            <p>{body_line}</p>
            <p><b>Email:</b> {email}</p>
            <p><b>Time:</b> {timestamp}</p>
            <p>— Pahad Guard</p>
          </body>
        </html>
    """

    return _send_email(email, subject, html_content)


def send_owner_notification(event: str, full_name: str, email: str) -> tuple[bool, str]:
    """Email the site owner (NOTIFY_EMAIL) when a user logs in or signs up.

    Optional: only sent if NOTIFY_EMAIL is configured in .env.
    """
    notify_email = os.getenv("NOTIFY_EMAIL")
    if not notify_email or notify_email == "you@example.com":
        return False, "NOTIFY_EMAIL is not configured in your .env file."

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    event_label = "New Sign Up" if event == "signup" else "New Login"

    subject = f"Pahad Guard — {event_label}: {full_name or email}"
    html_content = f"""
        <html>
          <body>
            <h2>{event_label}</h2>
            <p><b>Name:</b> {full_name or 'N/A'}</p>
            <p><b>Email:</b> {email}</p>
            <p><b>Time:</b> {timestamp}</p>
            <p>This is an automated notification from your Pahad Guard app.</p>
          </body>
        </html>
    """

    return _send_email(notify_email, subject, html_content)


def send_auth_notifications(event: str, full_name: str, email: str) -> list[str]:
    """Send both the user confirmation and (if configured) the owner alert.

    Returns a list of human-readable warning strings for any email that
    failed to send — an empty list means everything that was attempted
    succeeded. Never raises.
    """
    warnings = []

    user_sent, user_message = send_user_notification(event, full_name, email)
    if not user_sent:
        warnings.append(f"User notification not sent: {user_message}")

    # Owner alert is optional — only attempted if NOTIFY_EMAIL is set.
    if os.getenv("NOTIFY_EMAIL") and os.getenv("NOTIFY_EMAIL") != "you@example.com":
        owner_sent, owner_message = send_owner_notification(event, full_name, email)
        if not owner_sent:
            warnings.append(f"Owner notification not sent: {owner_message}")

    return warnings
