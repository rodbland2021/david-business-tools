import json
import sqlite3
from pathlib import Path

import server


def _read_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def _write_config(config_path: Path, config: dict):
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)


def register(mcp):
    @mcp.tool
    def setup_get_status() -> str:
        """Check which platforms are configured and working. Returns JSON with status for each platform."""
        config_path = server.BASE_DIR / "config.json"
        config = _read_config(config_path)

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
                from adapters.neto import NetoAdapter
                adapter = NetoAdapter(
                    url=neto_cfg["url"],
                    username=neto_cfg["username"],
                    api_key=neto_cfg["api_key"],
                )
                adapter.get_items(limit=1)
                result["neto"] = "connected"
            except Exception:
                pass

        # --- Kogan ---
        kogan_cfg = config.get("kogan", {})
        if kogan_cfg.get("seller_id") and kogan_cfg.get("seller_token"):
            result["kogan"] = "configured"
            try:
                from adapters.kogan import KoganAdapter
                adapter = KoganAdapter(
                    seller_id=kogan_cfg["seller_id"],
                    seller_token=kogan_cfg["seller_token"],
                    environment=kogan_cfg.get("environment", "production"),
                )
                adapter.get_categories()
                result["kogan"] = "connected"
            except Exception:
                pass

        # --- Gmail ---
        gmail_cfg = config.get("gmail", {})
        if gmail_cfg.get("client_id") and gmail_cfg.get("client_secret"):
            result["gmail"] = "configured"
            token_file = server.BASE_DIR / gmail_cfg.get("token_file", "data/gmail_token.json")
            if token_file.exists():
                try:
                    from adapters.gmail_adapter import GmailAdapter
                    adapter = GmailAdapter(
                        client_id=gmail_cfg["client_id"],
                        client_secret=gmail_cfg["client_secret"],
                        token_file=str(token_file),
                    )
                    adapter.get_unread(max_results=1)
                    result["gmail"] = "connected"
                except Exception:
                    pass

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

        config_path = server.BASE_DIR / "config.json"
        config = _read_config(config_path)
        config["neto"] = {
            "url": url,
            "username": username,
            "api_key": api_key,
        }
        _write_config(config_path, config)

        try:
            from adapters.neto import NetoAdapter
            adapter = NetoAdapter(url=url, username=username, api_key=api_key)
            data = adapter.get_items(limit=1)
            items = data.get("GetItem", {}).get("Item", [])
            count = len(items)
            return json.dumps({
                "status": "connected",
                "message": f"Neto connected. Found {count} product(s) in test query.",
            })
        except Exception as e:
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

        config_path = server.BASE_DIR / "config.json"
        config = _read_config(config_path)
        config["kogan"] = {
            "seller_id": seller_id,
            "seller_token": seller_token,
            "environment": environment,
        }
        _write_config(config_path, config)

        try:
            from adapters.kogan import KoganAdapter
            adapter = KoganAdapter(
                seller_id=seller_id,
                seller_token=seller_token,
                environment=environment,
            )
            data = adapter.get_categories()
            categories = data.get("results", []) if isinstance(data, dict) else data
            count = len(categories) if isinstance(categories, list) else 0
            return json.dumps({
                "status": "connected",
                "message": f"Kogan connected. Found {count} categories.",
            })
        except Exception as e:
            return json.dumps({
                "status": "configured",
                "error": f"Connection failed: {e}",
            })

    @mcp.tool
    def setup_configure_gmail(client_id: str, client_secret: str) -> str:
        """Save Gmail OAuth2 credentials to config. The user will need to complete browser-based authorization separately."""
        config_path = server.BASE_DIR / "config.json"
        config = _read_config(config_path)
        config["gmail"] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "token_file": "data/gmail_token.json",
        }
        _write_config(config_path, config)
        return json.dumps({
            "status": "configured",
            "message": (
                "Gmail credentials saved. Run the authorization step to complete setup: "
                "the user needs to open a browser URL to grant access."
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
        config_path = server.BASE_DIR / "config.json"
        config = _read_config(config_path)
        config["purchasing"] = {
            "per_transaction_limit": per_transaction_limit,
            "daily_limit": daily_limit,
            "weekly_limit": weekly_limit,
            "monthly_limit": monthly_limit,
            "require_approval": require_approval,
        }
        _write_config(config_path, config)

        conn = sqlite3.connect(server.BASE_DIR / "data" / "spending.db")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
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
        conn.close()

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
        config_path = server.BASE_DIR / "config.json"
        config = _read_config(config_path)

        if platform == "neto":
            neto_cfg = config.get("neto", {})
            if not (neto_cfg.get("url") and neto_cfg.get("username") and neto_cfg.get("api_key")):
                return json.dumps({"platform": "neto", "status": "failed", "details": "Not configured."})
            try:
                from adapters.neto import NetoAdapter
                adapter = NetoAdapter(
                    url=neto_cfg["url"],
                    username=neto_cfg["username"],
                    api_key=neto_cfg["api_key"],
                )
                data = adapter.get_items(limit=1)
                items = data.get("GetItem", {}).get("Item", [])
                return json.dumps({
                    "platform": "neto",
                    "status": "connected",
                    "details": f"API reachable. {len(items)} product(s) returned in test query.",
                })
            except Exception as e:
                return json.dumps({"platform": "neto", "status": "failed", "details": str(e)})

        elif platform == "kogan":
            kogan_cfg = config.get("kogan", {})
            if not (kogan_cfg.get("seller_id") and kogan_cfg.get("seller_token")):
                return json.dumps({"platform": "kogan", "status": "failed", "details": "Not configured."})
            try:
                from adapters.kogan import KoganAdapter
                adapter = KoganAdapter(
                    seller_id=kogan_cfg["seller_id"],
                    seller_token=kogan_cfg["seller_token"],
                    environment=kogan_cfg.get("environment", "production"),
                )
                data = adapter.get_categories()
                categories = data.get("results", []) if isinstance(data, dict) else data
                count = len(categories) if isinstance(categories, list) else 0
                return json.dumps({
                    "platform": "kogan",
                    "status": "connected",
                    "details": f"API reachable. {count} categories returned.",
                })
            except Exception as e:
                return json.dumps({"platform": "kogan", "status": "failed", "details": str(e)})

        elif platform == "gmail":
            gmail_cfg = config.get("gmail", {})
            if not (gmail_cfg.get("client_id") and gmail_cfg.get("client_secret")):
                return json.dumps({"platform": "gmail", "status": "failed", "details": "Not configured."})
            token_file = server.BASE_DIR / gmail_cfg.get("token_file", "data/gmail_token.json")
            if not token_file.exists():
                return json.dumps({
                    "platform": "gmail",
                    "status": "failed",
                    "details": "Credentials saved but authorization not completed. Token file missing.",
                })
            try:
                from adapters.gmail_adapter import GmailAdapter
                adapter = GmailAdapter(
                    client_id=gmail_cfg["client_id"],
                    client_secret=gmail_cfg["client_secret"],
                    token_file=str(token_file),
                )
                messages = adapter.get_unread(max_results=1)
                return json.dumps({
                    "platform": "gmail",
                    "status": "connected",
                    "details": f"Gmail API reachable. {len(messages)} unread message(s) in test query.",
                })
            except Exception as e:
                return json.dumps({"platform": "gmail", "status": "failed", "details": str(e)})

        else:
            return json.dumps({
                "platform": platform,
                "status": "failed",
                "details": "Unknown platform. Valid values: 'neto', 'kogan', 'gmail'.",
            })
