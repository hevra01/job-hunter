"""
Gmail sender using OAuth2.

First-time setup:
1. Go to Google Cloud Console → Create a project → Enable Gmail API
2. Create OAuth2 credentials (Desktop app) → Download as data/gmail_credentials.json
3. Run: python -m sender.gmail --setup
   This opens a browser, asks you to authorize, and saves data/gmail_token.json

Subsequent sends use the saved token (auto-refreshed).
"""
import base64
import logging
import mimetypes
import os
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS_FILE", "data/gmail_credentials.json")
TOKEN_FILE = os.environ.get("GMAIL_TOKEN_FILE", "data/gmail_token.json")


def _get_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    token_path = Path(TOKEN_FILE)
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDENTIALS_FILE).exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDENTIALS_FILE}. "
                    "Download from Google Cloud Console (OAuth2 Desktop app credentials)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _build_message(
    to: str,
    subject: str,
    body: str,
    sender: str,
    attachments: list[str],
) -> dict:
    msg = MIMEMultipart()
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    for path_str in attachments:
        path = Path(path_str)
        if not path.exists():
            logger.warning("Attachment not found, skipping: %s", path_str)
            continue
        mime_type, _ = mimetypes.guess_type(str(path))
        main_type = (mime_type or "application/octet-stream").split("/")[0]
        sub_type = (mime_type or "application/pdf").split("/")[1]

        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype=sub_type)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def send_email(
    to: str,
    subject: str,
    body: str,
    sender: str,
    attachments: list[str] = None,
) -> bool:
    """
    Send an email via Gmail API.
    Returns True on success, False on failure.
    """
    attachments = attachments or []
    try:
        service = _get_service()
        message = _build_message(to, subject, body, sender, attachments)
        service.users().messages().send(userId="me", body=message).execute()
        logger.info("Email sent to %s (subject: %s)", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


if __name__ == "__main__":
    if "--setup" in sys.argv:
        print("Starting Gmail OAuth setup...")
        try:
            svc = _get_service()
            profile = svc.users().getProfile(userId="me").execute()
            print(f"Authorized as: {profile['emailAddress']}")
            print(f"Token saved to: {TOKEN_FILE}")
        except Exception as e:
            print(f"Setup failed: {e}")
            sys.exit(1)
