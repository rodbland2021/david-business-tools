import sqlite3

import pytest

from tools.purchasing_tools import _check_limits, _log_purchase, _update_status, _get_summary


def _init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS spending_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS spending_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            per_transaction_limit REAL NOT NULL,
            monthly_budget REAL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            vendor TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'AUD',
            status TEXT DEFAULT 'pending',
            approved_by TEXT,
            receipt_url TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocked_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    default_categories = [
        ('office_supplies', 200.0),
        ('food_delivery', 80.0),
        ('groceries', 200.0),
        ('general', 100.0),
    ]
    for name, limit in default_categories:
        conn.execute(
            "INSERT OR IGNORE INTO spending_categories (name, per_transaction_limit) VALUES (?, ?)",
            (name, limit)
        )

    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "spending.db"
    _init_db(str(path))
    return str(path)


def test_check_limits_within_budget(db_path):
    result = _check_limits(db_path, "office_supplies")
    assert "error" not in result
    assert result["within_limits"] is True
    assert result["per_transaction_limit"] == 200.0
    assert result["category"] == "office_supplies"
    assert result["today_spent"] == 0.0


def test_log_purchase(db_path):
    result = _log_purchase(db_path, "Amazon", "office_supplies", "Printer paper", 45.99)
    assert result["id"] is not None
    assert result["status"] == "pending"
    assert result["amount"] == 45.99


def test_update_status(db_path):
    logged = _log_purchase(db_path, "Amazon", "office_supplies", "Printer paper", 45.99)
    result = _update_status(db_path, logged["id"], "approved")
    assert result["status"] == "approved"
    assert "error" not in result


def test_get_summary(db_path):
    logged = _log_purchase(db_path, "Amazon", "office_supplies", "Printer paper", 45.99)

    # Manually mark as completed so it shows in summary
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE purchase_log SET status = 'completed' WHERE id = ?",
        (logged["id"],)
    )
    conn.commit()
    conn.close()

    results = _get_summary(db_path, "today")
    assert len(results) >= 1

    office = next((r for r in results if r["category"] == "office_supplies"), None)
    assert office is not None
    assert office["total"] == 45.99
