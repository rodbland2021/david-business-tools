import json

import server
from adapters.gmail_adapter import GmailAdapter

_gmail = None


def _get_gmail() -> GmailAdapter:
    global _gmail
    if _gmail is None:
        from server import load_config
        config = load_config()
        cfg = config.get("gmail", {})
        auth_method = cfg.get("auth_method", "oauth")

        if auth_method == "service_account":
            _gmail = GmailAdapter(
                auth_method="service_account",
                service_account_file=cfg["service_account_file"],
                delegated_user=cfg["delegated_user"],
            )
        else:
            _gmail = GmailAdapter(
                auth_method="oauth",
                client_id=cfg.get("client_id"),
                client_secret=cfg.get("client_secret"),
                token_file=cfg.get("token_file", "data/gmail_token.json"),
            )
    return _gmail


def register(mcp):
    @mcp.tool
    def gmail_get_unread(label: str = "", max_results: int = 20) -> str:
        """Fetch unread emails. Optional label filter."""
        try:
            result = _get_gmail().get_unread(
                label=label or None,
                max_results=max_results,
            )
            return json.dumps(result, default=str)
        except RuntimeError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool
    def gmail_get_message(message_id: str) -> str:
        """Read a specific email by message ID. Returns full body text."""
        try:
            result = _get_gmail().get_message(message_id)
            return json.dumps(result, default=str)
        except RuntimeError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool
    def gmail_create_draft(
        to: str,
        subject: str,
        body: str,
        in_reply_to: str = "",
    ) -> str:
        """Create an email draft. Set in_reply_to to a message ID to thread the reply."""
        try:
            draft_id = _get_gmail().create_draft(
                to=to,
                subject=subject,
                body=body,
                in_reply_to=in_reply_to or None,
            )
            return json.dumps({"draft_id": draft_id})
        except RuntimeError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool
    def gmail_send_draft(draft_id: str) -> str:
        """Send a previously created draft."""
        try:
            result = _get_gmail().send_draft(draft_id)
            return json.dumps(result, default=str)
        except RuntimeError as e:
            return json.dumps({"error": str(e)})
