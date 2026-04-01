import sqlite3

import pytest

from tools.purchasing_tools import _check_limits, _log_purchase, _update_status, _get_summary


def _init_db(db_path):
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

        CREATE TABLE IF NOT EXISTS spending_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            per_transaction_limit REAL,
            daily_limit REAL,
            enabled INTEGER NOT NULL DEFAULT 1,
            notes TEXT
        );

        INSERT OR IGNORE INTO spending_categories (name, per_transaction_limit, daily_limit, notes) VALUES
            ('office_supplies', 200.00, 300.00, 'OfficeWorks'),
            ('food_delivery', 80.00, 120.00, 'Uber Eats'),
            ('groceries', 200.00, 200.00, 'Woolworths'),
            ('general', 100.00, 200.00, 'Catch-all');

        CREATE TABLE IF NOT EXISTS purchase_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            platform TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            approved_by TEXT,
            approved_at TEXT,
            completed_at TEXT,
            order_reference TEXT,
            receipt_url TEXT,
            notes TEXT,
            FOREIGN KEY (category) REFERENCES spending_categories(name)
        );

        CREATE TABLE IF NOT EXISTS blocked_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
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
    assert result["daily_limit"] == 300.0
    assert result["category"] == "office_supplies"
    assert result["today_spent"] == 0.0
    assert result["require_approval"] is True


def test_check_limits_unknown_category(db_path):
    result = _check_limits(db_path, "nonexistent")
    assert "error" in result


def test_log_purchase(db_path):
    result = _log_purchase(db_path, "Amazon", "office_supplies", "Printer paper", 45.99)
    assert result["id"] is not None
    assert result["status"] == "pending"
    assert result["amount"] == 45.99


def test_update_status_approved(db_path):
    logged = _log_purchase(db_path, "Amazon", "office_supplies", "Printer paper", 45.99)
    result = _update_status(db_path, logged["id"], "approved")
    assert result["status"] == "approved"
    assert result["approved_at"] is not None
    assert "error" not in result


def test_update_status_completed(db_path):
    logged = _log_purchase(db_path, "Amazon", "office_supplies", "Pens", 12.50)
    _update_status(db_path, logged["id"], "approved")
    result = _update_status(db_path, logged["id"], "completed")
    assert result["status"] == "completed"
    assert result["completed_at"] is not None


def test_update_status_not_found(db_path):
    result = _update_status(db_path, 9999, "approved")
    assert "error" in result


def test_get_summary(db_path):
    logged = _log_purchase(db_path, "Amazon", "office_supplies", "Printer paper", 45.99)

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


def test_check_limits_after_spending(db_path):
    _log_purchase(db_path, "OfficeWorks", "office_supplies", "Paper", 100.0)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE purchase_log SET status = 'approved'")
    conn.commit()
    conn.close()

    result = _check_limits(db_path, "office_supplies")
    assert result["today_spent"] == 100.0
    assert result["daily_remaining"] == 200.0  # 300 limit - 100 spent
    assert result["within_limits"] is True
