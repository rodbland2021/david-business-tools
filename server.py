import json
import os
import sqlite3
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("david-business-tools")

BASE_DIR = Path(__file__).parent


def load_config():
    config_path = BASE_DIR / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(
            "config.json not found. Copy config.example.json to config.json and fill in your credentials."
        )
    with open(config_path) as f:
        return json.load(f)


def get_products_db():
    conn = sqlite3.connect(BASE_DIR / "data" / "products.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def get_spending_db():
    conn = sqlite3.connect(BASE_DIR / "data" / "spending.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_products_db():
    conn = get_products_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            brand TEXT,
            model TEXT,
            description TEXT,
            specs JSON,
            price REAL,
            cost_price REAL,
            stock INTEGER DEFAULT 0,
            condition TEXT,
            category TEXT,
            images JSON,
            neto_synced_at TEXT,
            kogan_sku TEXT,
            kogan_synced_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def init_spending_db():
    conn = get_spending_db()

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

    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_purchase_log_category ON purchase_log (category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_purchase_log_status ON purchase_log (status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_purchase_log_created_at ON purchase_log (created_at)")

    # Spending totals view
    conn.execute("""
        CREATE VIEW IF NOT EXISTS spending_totals AS
        SELECT
            category,
            SUM(CASE WHEN status = 'approved' THEN amount ELSE 0 END) AS approved_total,
            SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END) AS pending_total,
            COUNT(*) AS transaction_count
        FROM purchase_log
        WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        GROUP BY category
    """)

    # Default categories
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


def main():
    init_products_db()
    init_spending_db()

    from tools.store_tools import register as register_store
    from tools.neto_tools import register as register_neto
    from tools.kogan_tools import register as register_kogan
    from tools.gmail_tools import register as register_gmail
    from tools.purchasing_tools import register as register_purchasing
    from tools.specs_tools import register as register_specs

    register_store(mcp)
    register_neto(mcp)
    register_kogan(mcp)
    register_gmail(mcp)
    register_purchasing(mcp)
    register_specs(mcp)

    mcp.run()


if __name__ == "__main__":
    main()
