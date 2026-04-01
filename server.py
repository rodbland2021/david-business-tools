import json
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
    conn.executescript("""
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
            ('food_delivery', 80.00, 120.00, 'Uber Eats, DoorDash, Menulog'),
            ('groceries', 200.00, 200.00, 'Woolworths, Coles online'),
            ('general', 100.00, 200.00, 'Catch-all for unlisted platforms');

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

        CREATE INDEX IF NOT EXISTS idx_purchase_log_date ON purchase_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_purchase_log_status ON purchase_log(status);

        CREATE VIEW IF NOT EXISTS spending_totals AS
        SELECT
            category,
            SUM(CASE WHEN created_at >= date('now') AND status IN ('approved','completed') THEN amount ELSE 0 END) as today_spent,
            SUM(CASE WHEN created_at >= date('now', '-7 days') AND status IN ('approved','completed') THEN amount ELSE 0 END) as week_spent,
            SUM(CASE WHEN created_at >= date('now', 'start of month') AND status IN ('approved','completed') THEN amount ELSE 0 END) as month_spent
        FROM purchase_log
        GROUP BY category;
    """)
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
    from tools.setup_tools import register as register_setup

    register_store(mcp)
    register_neto(mcp)
    register_kogan(mcp)
    register_gmail(mcp)
    register_purchasing(mcp)
    register_specs(mcp)
    register_setup(mcp)

    mcp.run()


if __name__ == "__main__":
    main()
