import json
import sqlite3

import pytest

import server
from tools.setup_tools import _read_config, _write_config, register


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect CONFIG_PATH and BASE_DIR to tmp_path for every test."""
    import tools.setup_tools as mod

    monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    return tmp_path


def _init_spending_db(tmp_path):
    db_path = tmp_path / "data" / "spending.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS spending_config (
            id INTEGER PRIMARY KEY,
            per_transaction_limit REAL NOT NULL DEFAULT 200.00,
            daily_limit REAL NOT NULL DEFAULT 500.00,
            weekly_limit REAL NOT NULL DEFAULT 1500.00,
            monthly_limit REAL NOT NULL DEFAULT 4000.00,
            require_approval INTEGER NOT NULL DEFAULT 1,
            auto_approve_below REAL DEFAULT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO spending_config (id) VALUES (1);
    """)
    conn.commit()
    conn.close()


class FakeMCP:
    """Minimal stand-in that captures tool registrations."""
    def __init__(self):
        self.tools = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


@pytest.fixture
def tools(isolate_config):
    fake = FakeMCP()
    register(fake)
    return fake.tools


# --- _read_config / _write_config ---

def test_read_config_missing_file(isolate_config):
    assert _read_config() == {}


def test_read_config_malformed_json(isolate_config):
    import tools.setup_tools as mod
    mod.CONFIG_PATH.write_text("{bad json")
    assert _read_config() == {}


def test_write_then_read_roundtrip(isolate_config):
    data = {"neto": {"url": "https://test.neto.com.au"}}
    _write_config(data)
    assert _read_config() == data


# --- setup_get_status ---

def test_get_status_no_config(tools):
    result = json.loads(tools["setup_get_status"]())
    assert result["neto"]["status"] == "not_configured"
    assert result["kogan"]["status"] == "not_configured"
    assert result["gmail"]["status"] == "not_configured"
    assert result["purchasing"]["status"] == "ready"
    # All entries have human-friendly messages
    assert "message" in result["neto"]
    assert "message" in result["purchasing"]


def test_get_status_with_partial_config(tools):
    _write_config({"neto": {"url": "https://x.neto.com.au", "username": "u", "api_key": "k"}})
    result = json.loads(tools["setup_get_status"]())
    # Connection will fail (no real API), but status should be "configured" not "not_configured"
    assert result["neto"]["status"] in ("configured", "connected")


# --- setup_configure_neto ---

def test_configure_neto_bad_url(tools):
    result = json.loads(tools["setup_configure_neto"](url="http://insecure.com", username="u", api_key="k"))
    assert result["status"] == "error"
    assert "https" in result["error"]


def test_configure_neto_saves_config(tools):
    # Will fail connection (no real API) but should save config
    result = json.loads(tools["setup_configure_neto"](
        url="https://test.neto.com.au", username="user1", api_key="key123"
    ))
    assert result["status"] in ("configured", "connected")

    saved = _read_config()
    assert saved["neto"]["url"] == "https://test.neto.com.au"
    assert saved["neto"]["username"] == "user1"
    assert saved["neto"]["api_key"] == "key123"


# --- setup_configure_kogan ---

def test_configure_kogan_bad_environment(tools):
    result = json.loads(tools["setup_configure_kogan"](
        seller_id="s1", seller_token="t1", environment="staging"
    ))
    assert result["status"] == "error"


def test_configure_kogan_saves_config(tools):
    result = json.loads(tools["setup_configure_kogan"](
        seller_id="seller123", seller_token="token456", environment="uat"
    ))
    assert result["status"] in ("configured", "connected")

    saved = _read_config()
    assert saved["kogan"]["seller_id"] == "seller123"
    assert saved["kogan"]["environment"] == "uat"


# --- setup_configure_gmail ---

def test_configure_gmail_saves_config(tools):
    result = json.loads(tools["setup_configure_gmail"](
        client_id="cid.apps.googleusercontent.com", client_secret="secret"
    ))
    assert result["status"] == "configured"
    assert "setup_gmail_authorize" in result["message"]

    saved = _read_config()
    assert saved["gmail"]["client_id"] == "cid.apps.googleusercontent.com"
    assert saved["gmail"]["token_file"] == "data/gmail_token.json"


# --- setup_configure_purchasing ---

def test_configure_purchasing_defaults(tools, isolate_config):
    _init_spending_db(isolate_config)
    result = json.loads(tools["setup_configure_purchasing"]())
    assert result["status"] == "ready"
    assert result["limits"]["per_transaction"] == 200.0
    assert result["limits"]["require_approval"] is True

    saved = _read_config()
    assert saved["purchasing"]["daily_limit"] == 500.0


def test_configure_purchasing_custom_limits(tools, isolate_config):
    _init_spending_db(isolate_config)
    result = json.loads(tools["setup_configure_purchasing"](
        per_transaction_limit=100.0,
        daily_limit=300.0,
        weekly_limit=1000.0,
        monthly_limit=3000.0,
        require_approval=False,
    ))
    assert result["status"] == "ready"
    assert result["limits"]["per_transaction"] == 100.0
    assert result["limits"]["require_approval"] is False

    # Verify DB was updated
    db_path = isolate_config / "data" / "spending.db"
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT * FROM spending_config WHERE id = 1").fetchone()
    conn.close()
    assert row[1] == 100.0  # per_transaction_limit
    assert row[5] == 0  # require_approval = False


def test_configure_purchasing_no_db_table(tools, isolate_config):
    """If spending_config table doesn't exist, the tool should raise, not silently succeed."""
    # Create DB file but don't create the table
    db_path = isolate_config / "data" / "spending.db"
    conn = sqlite3.connect(db_path)
    conn.close()

    with pytest.raises(Exception):
        tools["setup_configure_purchasing"]()


# --- setup_configure_purchasing (view current limits) ---

def test_configure_purchasing_defaults_returns_current_when_set(tools, isolate_config):
    _init_spending_db(isolate_config)
    # First call with custom limits saves them
    tools["setup_configure_purchasing"](per_transaction_limit=100.0, daily_limit=250.0,
                                        weekly_limit=800.0, monthly_limit=2000.0, require_approval=False)
    # Second call with all defaults should return the saved values, not write new ones
    result = json.loads(tools["setup_configure_purchasing"]())
    assert result["status"] == "ready"
    assert "current_limits" in result
    assert result["current_limits"]["per_transaction"] == 100.0
    assert result["current_limits"]["daily"] == 250.0


# --- setup_gmail_authorize / setup_gmail_complete_auth ---

def test_gmail_authorize_requires_config(tools):
    result = json.loads(tools["setup_gmail_authorize"]())
    assert "error" in result
    assert "setup_configure_gmail" in result["error"]


# --- setup_test_connection ---

def test_test_connection_not_configured(tools):
    result = json.loads(tools["setup_test_connection"](platform="neto"))
    assert result["status"] == "failed"
    assert "Not configured" in result["details"]


def test_test_connection_unknown_platform(tools):
    result = json.loads(tools["setup_test_connection"](platform="shopify"))
    assert result["status"] == "failed"
    assert "Unknown platform" in result["details"]


def test_test_connection_gmail_no_token(tools):
    _write_config({"gmail": {"client_id": "cid", "client_secret": "cs"}})
    result = json.loads(tools["setup_test_connection"](platform="gmail"))
    assert result["status"] == "failed"
    assert "authorization not completed" in result["details"]
