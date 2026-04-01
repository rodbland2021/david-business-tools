import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _get_conn(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _check_limits(db_path, category) -> dict:
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM spending_categories WHERE name = ? AND active = 1",
            (category,)
        ).fetchone()
        if not row:
            return {"error": f"Unknown category: {category}"}

        per_transaction_limit = row["per_transaction_limit"]

        # Get global limits from spending_config (key-value table)
        def cfg(key, default):
            r = conn.execute(
                "SELECT value FROM spending_config WHERE key = ?", (key,)
            ).fetchone()
            return float(r["value"]) if r else default

        daily_limit = cfg("daily_limit", 500.0)
        weekly_limit = cfg("weekly_limit", 1500.0)
        monthly_limit = cfg("monthly_limit", 4000.0)
        require_approval = cfg("require_approval_above", per_transaction_limit) < per_transaction_limit

        # Spending for this category today
        today_spent = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM purchase_log
               WHERE category = ?
               AND date(created_at) = date('now')
               AND status IN ('approved', 'completed')""",
            (category,)
        ).fetchone()[0]

        # Spending across ALL categories this week
        week_spent = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM purchase_log
               WHERE date(created_at) >= date('now', '-7 days')
               AND status IN ('approved', 'completed')"""
        ).fetchone()[0]

        # Spending across ALL categories this month
        month_spent = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM purchase_log
               WHERE date(created_at) >= date('now', 'start of month')
               AND status IN ('approved', 'completed')"""
        ).fetchone()[0]

        daily_remaining = max(0.0, daily_limit - today_spent)
        weekly_remaining = max(0.0, weekly_limit - week_spent)
        monthly_remaining = max(0.0, monthly_limit - month_spent)

        within_limits = (
            daily_remaining > 0
            and weekly_remaining > 0
            and monthly_remaining > 0
        )

        return {
            "category": category,
            "within_limits": within_limits,
            "per_transaction_limit": per_transaction_limit,
            "daily_limit": daily_limit,
            "today_spent": today_spent,
            "daily_remaining": daily_remaining,
            "week_spent": week_spent,
            "weekly_limit": weekly_limit,
            "weekly_remaining": weekly_remaining,
            "month_spent": month_spent,
            "monthly_limit": monthly_limit,
            "monthly_remaining": monthly_remaining,
            "require_approval": require_approval,
        }
    finally:
        conn.close()


def _log_purchase(db_path, platform, category, description, amount) -> dict:
    conn = _get_conn(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO purchase_log (vendor, category, description, amount, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (platform, category, description, amount)
        )
        conn.commit()
        return {"id": cur.lastrowid, "status": "pending", "amount": amount}
    finally:
        conn.close()


def _update_status(db_path, purchase_id, status) -> dict:
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM purchase_log WHERE id = ?", (purchase_id,)
        ).fetchone()
        if not row:
            return {"error": "Purchase not found"}

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE purchase_log SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, purchase_id)
        )
        conn.commit()

        updated = conn.execute(
            "SELECT * FROM purchase_log WHERE id = ?", (purchase_id,)
        ).fetchone()
        return dict(updated)
    finally:
        conn.close()


def _get_summary(db_path, period="today") -> list:
    conn = _get_conn(db_path)
    try:
        if period == "today":
            date_filter = "date(created_at) = date('now')"
        elif period == "week":
            date_filter = "date(created_at) >= date('now', '-7 days')"
        elif period == "month":
            date_filter = "date(created_at) >= date('now', 'start of month')"
        else:
            date_filter = "date(created_at) = date('now')"

        rows = conn.execute(
            f"""SELECT category, SUM(amount) AS total, COUNT(*) AS count
                FROM purchase_log
                WHERE {date_filter}
                AND status IN ('approved', 'completed')
                GROUP BY category"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def register(mcp):
    import json

    import server

    @mcp.tool
    def purchasing_check_limits(category: str) -> str:
        """Check remaining spending budget for a category. Categories: office_supplies, food_delivery, groceries, general."""
        db_path = server.BASE_DIR / "data" / "spending.db"
        result = _check_limits(db_path, category)
        return json.dumps(result)

    @mcp.tool
    def purchasing_log_purchase(
        platform: str,
        category: str,
        description: str,
        amount: float,
    ) -> str:
        """Record a purchase in the spending log. Status starts as 'pending'."""
        db_path = server.BASE_DIR / "data" / "spending.db"
        result = _log_purchase(db_path, platform, category, description, amount)
        return json.dumps(result)

    @mcp.tool
    def purchasing_update_status(purchase_id: int, status: str) -> str:
        """Update a purchase status. Values: approved, completed, rejected, cancelled."""
        db_path = server.BASE_DIR / "data" / "spending.db"
        result = _update_status(db_path, purchase_id, status)
        return json.dumps(result, default=str)

    @mcp.tool
    def purchasing_get_summary(period: str = "today") -> str:
        """Get spending summary. period: 'today', 'week', or 'month'."""
        db_path = server.BASE_DIR / "data" / "spending.db"
        result = _get_summary(db_path, period)
        return json.dumps(result)
