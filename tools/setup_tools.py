import json
import logging
import sqlite3

import server

logger = logging.getLogger(__name__)

CONFIG_PATH = server.BASE_DIR / "config.json"


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

    token_file = server.BASE_DIR / gmail_cfg.get("token_file", "data/gmail_token.json")
    if not token_file.exists():
        return {"error": "Credentials saved but authorization not completed. Token file missing."}

    adapter = GmailAdapter(
        client_id=gmail_cfg["client_id"],
        client_secret=gmail_cfg["client_secret"],
        token_file=str(token_file),
    )
    messages = adapter.get_unread(max_results=1)
    return {"count": len(messages)}


def register(mcp):
    @mcp.tool
    def setup_get_status() -> str:
        """Check which platforms are configured and working. Returns JSON with status for each platform."""
        config = _read_config()

        result = {
            "neto": "not_configured",
            "kogan": "not_configured",
            "gmail": "not_configured",
            "purchasing": "ready",
        }

        # --- Neto ---
        neto_cfg = config.get("neto", {})
        if neto_cfg.get("url") and neto_cfg.get("username") and neto_cfg.get("api_key"):
            result["neto"] = "configured"
            try:
                _test_neto(neto_cfg)
                result["neto"] = "connected"
            except Exception as e:
                logger.warning("Neto connection check failed: %s", e)

        # --- Kogan ---
        kogan_cfg = config.get("kogan", {})
        if kogan_cfg.get("seller_id") and kogan_cfg.get("seller_token"):
            result["kogan"] = "configured"
            try:
                _test_kogan(kogan_cfg)
                result["kogan"] = "connected"
            except Exception as e:
                logger.warning("Kogan connection check failed: %s", e)

        # --- Gmail ---
        gmail_cfg = config.get("gmail", {})
        if gmail_cfg.get("client_id") and gmail_cfg.get("client_secret"):
            result["gmail"] = "configured"
            try:
                info = _test_gmail(gmail_cfg)
                if "error" not in info:
                    result["gmail"] = "connected"
            except Exception as e:
                logger.warning("Gmail connection check failed: %s", e)

        return json.dumps(result)

    @mcp.tool
    def setup_configure_neto(url: str, username: str, api_key: str) -> str:
        """Configure Neto credentials and test the connection. url must be an https:// Neto store URL."""
        url = url.strip()
        if not url.startswith("https://"):
            return json.dumps({"status": "error", "error": "URL must start with https://"})
        if ".neto.com.au" not in url and ".maropost.com" not in url:
            # Warn but don't block — some stores use custom domains
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
        """Configure Kogan marketplace credentials and test the connection. environment: 'production' or 'uat'."""
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
    def setup_configure_gmail(client_id: str, client_secret: str) -> str:
        """Save Gmail OAuth2 credentials to config. The user will need to complete browser-based authorization separately."""
        config = _read_config()
        config["gmail"] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "token_file": "data/gmail_token.json",
        }
        _write_config(config)
        logger.info("Gmail OAuth credentials saved")
        return json.dumps({
            "status": "configured",
            "message": (
                "Gmail credentials saved. To complete authorization, run this command "
                "on David's machine (it will open a browser window for Google consent):\n\n"
                "  python3 -c \""
                "import json, sys; sys.path.insert(0, '.'); "
                "from adapters.gmail_adapter import GmailAdapter; "
                "cfg = json.load(open('config.json'))['gmail']; "
                "GmailAdapter(cfg['client_id'], cfg['client_secret'], cfg['token_file']).authorize(); "
                "print('Gmail authorized successfully')\""
            ),
        })

    @mcp.tool
    def setup_configure_purchasing(
        per_transaction_limit: float = 200.0,
        daily_limit: float = 500.0,
        weekly_limit: float = 1500.0,
        monthly_limit: float = 4000.0,
        require_approval: bool = True,
    ) -> str:
        """Configure purchasing spending limits and save them to both config.json and spending.db."""
        # Write DB first — if this fails, config.json stays unchanged
        db_path = server.BASE_DIR / "data" / "spending.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            # Ensure the config row exists (handles first-run case)
            conn.execute("""
                INSERT OR IGNORE INTO spending_config (id) VALUES (1)
            """)

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

        # DB succeeded — now update config.json
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
