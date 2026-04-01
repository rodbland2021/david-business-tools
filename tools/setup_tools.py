import json
import logging
import sqlite3
from pathlib import Path

import server

logger = logging.getLogger(__name__)

CONFIG_PATH = server.BASE_DIR / "config.json"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Malformed config.json, starting fresh: %s", e)
        return {}


def _write_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


def _test_neto(neto_cfg: dict) -> dict:
    from adapters.neto import NetoAdapter

    adapter = NetoAdapter(
        url=neto_cfg["url"],
        username=neto_cfg["username"],
        api_key=neto_cfg["api_key"],
    )
    data = adapter.get_items(limit=1)
    items = data.get("GetItem", {}).get("Item", [])
    return {"count": len(items)}


def _test_kogan(kogan_cfg: dict) -> dict:
    from adapters.kogan import KoganAdapter

    adapter = KoganAdapter(
        seller_id=kogan_cfg["seller_id"],
        seller_token=kogan_cfg["seller_token"],
        environment=kogan_cfg.get("environment", "production"),
    )
    data = adapter.get_categories()
    categories = data.get("results", []) if isinstance(data, dict) else data
    count = len(categories) if isinstance(categories, list) else 0
    return {"count": count}


def _test_gmail(gmail_cfg: dict) -> dict:
    from adapters.gmail_adapter import GmailAdapter

    auth_method = gmail_cfg.get("auth_method", "oauth")

    if auth_method == "service_account":
        sa_file = gmail_cfg.get("service_account_file", "")
        delegated_user = gmail_cfg.get("delegated_user", "")
        if not sa_file or not delegated_user:
            return {"error": "Service account config incomplete. Both service_account_file and delegated_user are required."}
        sa_path = server.BASE_DIR / sa_file if not sa_file.startswith("/") else Path(sa_file)
        if not sa_path.exists():
            return {"error": f"Service account file not found: {sa_path}"}
        adapter = GmailAdapter(
            auth_method="service_account",
            service_account_file=str(sa_path),
            delegated_user=delegated_user,
        )
    else:
        token_file = server.BASE_DIR / gmail_cfg.get("token_file", "data/gmail_token.json")
        if not token_file.exists():
            return {"error": "Credentials saved but authorization not completed. Token file missing."}
        adapter = GmailAdapter(
            auth_method="oauth",
            client_id=gmail_cfg["client_id"],
            client_secret=gmail_cfg["client_secret"],
            token_file=str(token_file),
        )

    messages = adapter.get_unread(max_results=1)
    return {"count": len(messages)}


def _gmail_client_config(gmail_cfg: dict) -> dict:
    return {
        "installed": {
            "client_id": gmail_cfg["client_id"],
            "client_secret": gmail_cfg["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }


def _invalidate_gmail_singleton():
    """Clear the cached Gmail adapter so gmail tools pick up new config."""
    try:
        from tools.gmail_tools import reset_gmail
        reset_gmail()
    except ImportError:
        pass


def register(mcp):
    @mcp.tool
    def setup_get_status() -> str:
        """Check which platforms are configured and working. Returns JSON with status and human-friendly message for each platform."""
        config = _read_config()

        _STATUS_MESSAGES = {
            "neto": {
                "not_configured": "Not set up yet. You'll need your Neto store URL, API username, and API key.",
                "configured": "Credentials saved but connection not verified.",
                "connected": "Connected and working.",
            },
            "kogan": {
                "not_configured": "Not set up yet. You'll need your Kogan Seller ID and Seller Token.",
                "configured": "Credentials saved but connection not verified.",
                "connected": "Connected and working.",
            },
            "gmail": {
                "not_configured": "Not set up yet. You'll need Google OAuth credentials (client ID and secret) or a service account key file.",
                "configured": "Credentials saved. Browser authorization still needed (OAuth) or connection not verified (service account).",
                "connected": "Connected and working.",
            },
        }

        neto_status = "not_configured"
        kogan_status = "not_configured"
        gmail_status = "not_configured"

        # --- Neto ---
        neto_cfg = config.get("neto", {})
        if neto_cfg.get("url") and neto_cfg.get("username") and neto_cfg.get("api_key"):
            neto_status = "configured"
            try:
                _test_neto(neto_cfg)
                neto_status = "connected"
            except Exception as e:
                logger.warning("Neto connection check failed: %s", e)

        # --- Kogan ---
        kogan_cfg = config.get("kogan", {})
        if kogan_cfg.get("seller_id") and kogan_cfg.get("seller_token"):
            kogan_status = "configured"
            try:
                _test_kogan(kogan_cfg)
                kogan_status = "connected"
            except Exception as e:
                logger.warning("Kogan connection check failed: %s", e)

        # --- Gmail ---
        gmail_cfg = config.get("gmail", {})
        auth_method = gmail_cfg.get("auth_method", "oauth")
        if auth_method == "service_account":
            if gmail_cfg.get("service_account_file") and gmail_cfg.get("delegated_user"):
                gmail_status = "configured"
                try:
                    info = _test_gmail(gmail_cfg)
                    if "error" not in info:
                        gmail_status = "connected"
                except Exception as e:
                    logger.warning("Gmail connection check failed: %s", e)
        else:
            if gmail_cfg.get("client_id") and gmail_cfg.get("client_secret"):
                gmail_status = "configured"
                try:
                    info = _test_gmail(gmail_cfg)
                    if "error" not in info:
                        gmail_status = "connected"
                except Exception as e:
                    logger.warning("Gmail connection check failed: %s", e)

        result = {
            "neto": {
                "status": neto_status,
                "message": _STATUS_MESSAGES["neto"][neto_status],
            },
            "kogan": {
                "status": kogan_status,
                "message": _STATUS_MESSAGES["kogan"][kogan_status],
            },
            "gmail": {
                "status": gmail_status,
                "message": _STATUS_MESSAGES["gmail"][gmail_status],
            },
            "purchasing": {
                "status": "ready",
                "message": "Ready to use. Default limits: $200/transaction, $500/day, $1500/week, $4000/month.",
            },
        }

        return json.dumps(result)

    @mcp.tool
    def setup_configure_neto(url: str, username: str, api_key: str) -> str:
        """Configure Neto credentials and test the connection. url must be an https:// Neto store URL.

        Where to find these credentials: Log into your Neto control panel → Settings & Tools → All Settings & Tools → API → Add New Key. Set permissions to read/write for Products, Orders, and RMA. Copy the generated key. The URL is your store URL (e.g., https://yourstore.neto.com.au). The username is the API user you created.
        """
        url = url.strip()
        if not url.startswith("https://"):
            return json.dumps({"status": "error", "error": "URL must start with https://"})
        if ".neto.com.au" not in url and ".maropost.com" not in url:
            pass

        config = _read_config()
        config["neto"] = {
            "url": url,
            "username": username,
            "api_key": api_key,
        }
        _write_config(config)

        try:
            info = _test_neto(config["neto"])
            logger.info("Neto configured and connected (%d products in test query)", info["count"])
            return json.dumps({
                "status": "connected",
                "message": f"Neto connected. Found {info['count']} product(s) in test query.",
            })
        except Exception as e:
            logger.warning("Neto configured but connection failed: %s", e)
            return json.dumps({
                "status": "configured",
                "error": f"Connection failed: {e}",
            })

    @mcp.tool
    def setup_configure_kogan(
        seller_id: str,
        seller_token: str,
        environment: str = "production",
    ) -> str:
        """Configure Kogan marketplace credentials and test the connection. environment: 'production' or 'uat'.

        Where to find these credentials: Log into Kogan Seller Portal → Settings → API Access. Copy your Seller ID and Seller Token. Use environment='uat' for testing, 'production' for live.
        """
        environment = environment.strip().lower()
        if environment not in ("production", "uat"):
            return json.dumps({
                "status": "error",
                "error": "environment must be 'production' or 'uat'",
            })

        config = _read_config()
        config["kogan"] = {
            "seller_id": seller_id,
            "seller_token": seller_token,
            "environment": environment,
        }
        _write_config(config)

        try:
            info = _test_kogan(config["kogan"])
            logger.info("Kogan configured and connected (%d categories)", info["count"])
            return json.dumps({
                "status": "connected",
                "message": f"Kogan connected. Found {info['count']} categories.",
            })
        except Exception as e:
            logger.warning("Kogan configured but connection failed: %s", e)
            return json.dumps({
                "status": "configured",
                "error": f"Connection failed: {e}",
            })

    @mcp.tool
    def setup_configure_gmail(
        auth_method: str = "oauth",
        client_id: str = "",
        client_secret: str = "",
        service_account_file: str = "",
        delegated_user: str = "",
    ) -> str:
        """Configure Gmail email integration. Two authentication methods are available:

        1. OAuth (for personal Gmail / @gmail.com accounts):
           - Requires client_id and client_secret from Google Cloud Console
           - One-time browser authorization needed after configuration
           - Go to console.cloud.google.com → APIs & Services → Credentials → Create OAuth 2.0 Client ID (type: Desktop App). Enable the Gmail API. Copy client_id and client_secret.

        2. Service Account (for Google Workspace / business email):
           - Requires a service account JSON key file and the email address to access
           - No browser authorization needed — works immediately
           - Setup: Google Workspace Admin → Security → API Controls → Domain-wide Delegation
           - Add the service account's client ID with scopes: gmail.readonly, gmail.compose, gmail.modify
        """
        auth_method = auth_method.strip().lower()
        if auth_method not in ("oauth", "service_account"):
            return json.dumps({
                "status": "error",
                "error": "auth_method must be 'oauth' or 'service_account'",
            })

        config = _read_config()

        if auth_method == "service_account":
            if not service_account_file or not delegated_user:
                return json.dumps({
                    "status": "error",
                    "error": "service_account_file and delegated_user are required for service_account auth",
                })
            sa_path = server.BASE_DIR / service_account_file if not service_account_file.startswith("/") else Path(service_account_file)
            if not sa_path.exists():
                return json.dumps({
                    "status": "error",
                    "error": f"Service account file not found: {service_account_file}",
                })
            config["gmail"] = {
                "auth_method": "service_account",
                "service_account_file": str(sa_path),
                "delegated_user": delegated_user,
            }
            _write_config(config)
            _invalidate_gmail_singleton()
            logger.info("Gmail service account credentials saved for %s", delegated_user)
            return json.dumps({
                "status": "configured",
                "message": (
                    f"Gmail service account configured for {delegated_user}. "
                    "No browser authorization needed. Run setup_test_connection to verify."
                ),
            })
        else:
            if not client_id or not client_secret:
                return json.dumps({
                    "status": "error",
                    "error": "client_id and client_secret are required for oauth auth",
                })
            config["gmail"] = {
                "auth_method": "oauth",
                "client_id": client_id,
                "client_secret": client_secret,
                "token_file": "data/gmail_token.json",
            }
            _write_config(config)
            _invalidate_gmail_singleton()
            logger.info("Gmail OAuth credentials saved")
            return json.dumps({
                "status": "configured",
                "message": (
                    "Gmail credentials saved. Run setup_gmail_authorize to get a URL to open in your browser. "
                    "After granting access, copy the authorization code and pass it to setup_gmail_complete_auth."
                ),
            })

    @mcp.tool
    def setup_gmail_authorize() -> str:
        """Start Gmail OAuth authorization. Returns a URL the user must open in their browser.
        After granting access, the browser will show an authorization code.
        Copy that code and pass it to setup_gmail_complete_auth.
        Not needed for service account auth."""
        config = _read_config()
        gmail_cfg = config.get("gmail", {})

        if gmail_cfg.get("auth_method") == "service_account":
            return json.dumps({
                "error": "Authorization not needed for service account auth. Service accounts use domain-wide delegation."
            })

        if not gmail_cfg.get("client_id") or not gmail_cfg.get("client_secret"):
            return json.dumps({"error": "Gmail not configured yet. Run setup_configure_gmail first."})

        from google_auth_oauthlib.flow import InstalledAppFlow

        client_config = _gmail_client_config(gmail_cfg)
        flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        return json.dumps({
            "status": "awaiting_authorization",
            "auth_url": auth_url,
            "message": (
                "Open this URL in a browser, sign in with the Gmail account, grant access, "
                "then copy the authorization code and pass it to setup_gmail_complete_auth."
            ),
        })

    @mcp.tool
    def setup_gmail_complete_auth(auth_code: str) -> str:
        """Complete Gmail OAuth authorization by exchanging the code from the browser for access tokens.
        The auth_code is the code shown in the browser after granting access.
        Not needed for service account auth."""
        config = _read_config()
        gmail_cfg = config.get("gmail", {})

        if gmail_cfg.get("auth_method") == "service_account":
            return json.dumps({
                "error": "Authorization not needed for service account auth. Service accounts use domain-wide delegation."
            })

        if not gmail_cfg.get("client_id") or not gmail_cfg.get("client_secret"):
            return json.dumps({"error": "Gmail not configured. Run setup_configure_gmail first."})

        from google_auth_oauthlib.flow import InstalledAppFlow

        client_config = _gmail_client_config(gmail_cfg)
        flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        flow.fetch_token(code=auth_code.strip())

        token_file = server.BASE_DIR / gmail_cfg.get("token_file", "data/gmail_token.json")
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as f:
            f.write(flow.credentials.to_json())

        logger.info("Gmail token saved to %s", token_file)
        return json.dumps({
            "status": "connected",
            "message": "Gmail authorized successfully. Token saved. Email tools are now ready to use.",
        })

    @mcp.tool
    def setup_configure_purchasing(
        per_transaction_limit: float = 200.0,
        daily_limit: float = 500.0,
        weekly_limit: float = 1500.0,
        monthly_limit: float = 4000.0,
        require_approval: bool = True,
    ) -> str:
        """Configure purchasing spending limits and save them to both config.json and spending.db.
        Call with no arguments to see current limits."""
        called_with_defaults = (
            per_transaction_limit == 200.0
            and daily_limit == 500.0
            and weekly_limit == 1500.0
            and monthly_limit == 4000.0
            and require_approval is True
        )
        if called_with_defaults:
            existing = _read_config().get("purchasing", {})
            if existing:
                current_limits = {
                    "per_transaction": existing.get("per_transaction_limit", 200.0),
                    "daily": existing.get("daily_limit", 500.0),
                    "weekly": existing.get("weekly_limit", 1500.0),
                    "monthly": existing.get("monthly_limit", 4000.0),
                    "require_approval": existing.get("require_approval", True),
                }
                return json.dumps({"status": "ready", "current_limits": current_limits})

        db_path = server.BASE_DIR / "data" / "spending.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            conn.execute("INSERT OR IGNORE INTO spending_config (id) VALUES (1)")

            cursor = conn.execute("""
                UPDATE spending_config SET
                    per_transaction_limit = ?,
                    daily_limit = ?,
                    weekly_limit = ?,
                    monthly_limit = ?,
                    require_approval = ?,
                    updated_at = datetime('now')
                WHERE id = 1
            """, (
                per_transaction_limit,
                daily_limit,
                weekly_limit,
                monthly_limit,
                1 if require_approval else 0,
            ))
            conn.commit()
            if cursor.rowcount == 0:
                raise RuntimeError("spending_config table missing — run server.py once to initialize databases")
        except Exception:
            conn.close()
            raise
        conn.close()

        config = _read_config()
        config["purchasing"] = {
            "per_transaction_limit": per_transaction_limit,
            "daily_limit": daily_limit,
            "weekly_limit": weekly_limit,
            "monthly_limit": monthly_limit,
            "require_approval": require_approval,
        }
        _write_config(config)

        logger.info(
            "Purchasing limits configured: per_txn=%.2f daily=%.2f weekly=%.2f monthly=%.2f approval=%s",
            per_transaction_limit, daily_limit, weekly_limit, monthly_limit, require_approval,
        )
        limits = {
            "per_transaction": per_transaction_limit,
            "daily": daily_limit,
            "weekly": weekly_limit,
            "monthly": monthly_limit,
            "require_approval": require_approval,
        }
        return json.dumps({"status": "ready", "limits": limits})

    @mcp.tool
    def setup_test_connection(platform: str) -> str:
        """Test a specific platform connection. platform: 'neto', 'kogan', or 'gmail'."""
        platform = platform.strip().lower()
        config = _read_config()

        if platform == "neto":
            neto_cfg = config.get("neto", {})
            if not (neto_cfg.get("url") and neto_cfg.get("username") and neto_cfg.get("api_key")):
                return json.dumps({"platform": "neto", "status": "failed", "details": "Not configured."})
            try:
                info = _test_neto(neto_cfg)
                return json.dumps({
                    "platform": "neto",
                    "status": "connected",
                    "details": f"API reachable. {info['count']} product(s) returned in test query.",
                })
            except Exception as e:
                return json.dumps({"platform": "neto", "status": "failed", "details": str(e)})

        elif platform == "kogan":
            kogan_cfg = config.get("kogan", {})
            if not (kogan_cfg.get("seller_id") and kogan_cfg.get("seller_token")):
                return json.dumps({"platform": "kogan", "status": "failed", "details": "Not configured."})
            try:
                info = _test_kogan(kogan_cfg)
                return json.dumps({
                    "platform": "kogan",
                    "status": "connected",
                    "details": f"API reachable. {info['count']} categories returned.",
                })
            except Exception as e:
                return json.dumps({"platform": "kogan", "status": "failed", "details": str(e)})

        elif platform == "gmail":
            gmail_cfg = config.get("gmail", {})
            auth_method = gmail_cfg.get("auth_method", "oauth")

            if auth_method == "service_account":
                if not (gmail_cfg.get("service_account_file") and gmail_cfg.get("delegated_user")):
                    return json.dumps({"platform": "gmail", "status": "failed", "details": "Not configured."})
            else:
                if not (gmail_cfg.get("client_id") and gmail_cfg.get("client_secret")):
                    return json.dumps({"platform": "gmail", "status": "failed", "details": "Not configured."})

            try:
                info = _test_gmail(gmail_cfg)
                if "error" in info:
                    return json.dumps({"platform": "gmail", "status": "failed", "details": info["error"]})
                return json.dumps({
                    "platform": "gmail",
                    "status": "connected",
                    "details": f"Gmail API reachable. {info['count']} unread message(s) in test query.",
                })
            except Exception as e:
                return json.dumps({"platform": "gmail", "status": "failed", "details": str(e)})

        else:
            return json.dumps({
                "platform": platform,
                "status": "failed",
                "details": "Unknown platform. Valid values: 'neto', 'kogan', 'gmail'.",
            })
