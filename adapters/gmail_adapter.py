import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailAdapter:
    def __init__(self, auth_method: str = "oauth",
                 # OAuth params
                 client_id: str = None, client_secret: str = None, token_file: str = None,
                 # Service account params
                 service_account_file: str = None, delegated_user: str = None):
        self.auth_method = auth_method
        self._service = None

        if auth_method == "service_account":
            self.service_account_file = service_account_file
            self.delegated_user = delegated_user
        else:
            self.client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                }
            }
            self.token_file = Path(token_file) if token_file else None

    def _get_service(self):
        if self._service:
            return self._service

        if self.auth_method == "service_account":
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=SCOPES,
                subject=self.delegated_user,
            )
            self._service = build("gmail", "v1", credentials=creds)
            return self._service

        # OAuth flow
        creds = None

        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                raise RuntimeError(
                    f"Gmail token refresh failed: {e}. "
                    "Run authorize() to re-authenticate."
                )

        if not creds or not creds.valid:
            raise RuntimeError(
                "No valid Gmail credentials. Run authorize() first to complete OAuth consent."
            )

        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(creds.to_json())

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def authorize(self):
        if self.auth_method == "service_account":
            raise RuntimeError(
                "authorize() is not needed for service account auth. "
                "Service accounts use domain-wide delegation and do not require browser consent."
            )
        flow = InstalledAppFlow.from_client_config(self.client_config, SCOPES)
        creds = flow.run_local_server(port=0)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(creds.to_json())
        return True

    def get_unread(self, label=None, max_results=20) -> list:
        service = self._get_service()
        query = "is:unread"
        if label:
            query = f"{query} label:{label}"

        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = response.get("messages", [])

        results = []
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata",
                     metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            results.append({
                "id": detail["id"],
                "thread_id": detail["threadId"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": detail.get("snippet", ""),
            })
        return results

    def get_message(self, message_id) -> dict:
        service = self._get_service()
        detail = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        payload = detail.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        body = ""
        parts = payload.get("parts", [])
        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                        break
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        return {
            "id": detail["id"],
            "thread_id": detail["threadId"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }

    def create_draft(self, to, subject, body, in_reply_to=None) -> str:
        service = self._get_service()

        msg = MIMEText(body)
        msg["To"] = to
        msg["Subject"] = subject

        thread_id = None
        if in_reply_to:
            orig = service.users().messages().get(
                userId="me", id=in_reply_to, format="metadata",
                metadataHeaders=["Message-ID"]
            ).execute()
            orig_headers = {h["name"]: h["value"] for h in orig.get("payload", {}).get("headers", [])}
            rfc_message_id = orig_headers.get("Message-ID", "")
            if rfc_message_id:
                msg["In-Reply-To"] = rfc_message_id
                msg["References"] = rfc_message_id
            thread_id = orig.get("threadId")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        draft_body = {"message": {"raw": raw}}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id

        draft = service.users().drafts().create(userId="me", body=draft_body).execute()
        return draft["id"]

    def send_draft(self, draft_id) -> dict:
        service = self._get_service()
        result = service.users().drafts().send(userId="me", body={"id": draft_id}).execute()
        return {
            "id": result["id"],
            "thread_id": result["threadId"],
        }

    def mark_read(self, message_id):
        service = self._get_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
