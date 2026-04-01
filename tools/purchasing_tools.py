import json
import sqlite3
from datetime import datetime, timezone


def _get_conn(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _check_limits(db_path, category, amount=None) -> dict:
    conn = _get_conn(db_path)
    try:
        cat = conn.execute(
            "SELECT * FROM spending_categories WHERE name = ? AND enabled = 1",
            (category,)
        ).fetchone()
        if not cat:
            return {"error": f"Unknown category: {category}"}

        config = conn.execute("SELECT * FROM spending_config WHERE id = 1").fetchone()
        if not config:
            return {"error": "Spending config not initialized"}

        per_transaction_limit = cat["per_transaction_limit"] or config["per_transaction_limit"]
        cat_daily_limit = cat["daily_limit"] or config["daily_limit"]

        today_spent = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM purchase_log
               WHERE category = ?
               AND date(created_at) = date('now')
               AND status IN ('approved', 'completed')""",
            (category,)
        ).fetchone()[0]

        week_spent = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM purchase_log
               WHERE date(created_at) >= date('now', '-7 days')
               AND status IN ('approved', 'completed')"""
        ).fetchone()[0]

        month_spent = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM purchase_log
               WHERE date(created_at) >= date('now', 'start of month')
               AND status IN ('approved', 'completed')"""
        ).fetchone()[0]

        daily_remaining = max(0.0, cat_daily_limit - today_spent)
        weekly_remaining = max(0.0, config["weekly_limit"] - week_spent)
        monthly_remaining = max(0.0, config["monthly_limit"] - month_spent)

        within_limits = (
            daily_remaining > 0
            and weekly_remaining > 0
            and monthly_remaining > 0
        )

        result = {
            "category": category,
            "within_limits": within_limits,
            "per_transaction_limit": per_transaction_limit,
            "daily_limit": cat_daily_limit,
            "today_spent": today_spent,
            "daily_remaining": daily_remaining,
            "week_spent": week_spent,
            "weekly_limit": config["weekly_limit"],
            "weekly_remaining": weekly_remaining,
            "month_spent": month_spent,
            "monthly_limit": config["monthly_limit"],
            "monthly_remaining": monthly_remaining,
            "require_approval": bool(config["require_approval"]),
        }

        if amount is not None:
            would_exceed_transaction = amount > per_transaction_limit
            would_exceed_daily = (today_spent + amount) > cat_daily_limit
            would_exceed_weekly = (week_spent + amount) > config["weekly_limit"]
            would_exceed_monthly = (month_spent + amount) > config["monthly_limit"]
            result["would_exceed_transaction"] = would_exceed_transaction
            result["would_exceed_daily"] = would_exceed_daily
            result["would_exceed_weekly"] = would_exceed_weekly
            result["would_exceed_monthly"] = would_exceed_monthly
            result["can_purchase"] = not any([
                would_exceed_transaction,
                would_exceed_daily,
                would_exceed_weekly,
                would_exceed_monthly,
            ])

        return result
    finally:
        conn.close()


def _log_purchase(db_path, platform, category, description, amount) -> dict:
    conn = _get_conn(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO purchase_log (platform, category, description, amount, status)
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
        if status == "approved":
            conn.execute(
                "UPDATE purchase_log SET status = ?, approved_at = ? WHERE id = ?",
                (status, now, purchase_id)
            )
        elif status == "completed":
            conn.execute(
                "UPDATE purchase_log SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, purchase_id)
            )
        else:
            conn.execute(
                "UPDATE purchase_log SET status = ? WHERE id = ?",
                (status, purchase_id)
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

    import server

    @mcp.tool
    def purchasing_check_limits(category: str, amount: float = None) -> str:
        """Check remaining spending budget for a category. Optionally pass amount to check if a specific purchase would be allowed. Categories: office_supplies, food_delivery, groceries, general."""
        db_path = server.BASE_DIR / "data" / "spending.db"
        result = _check_limits(str(db_path), category, amount=amount)
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
        result = _log_purchase(str(db_path), platform, category, description, amount)
        return json.dumps(result)

    @mcp.tool
    def purchasing_update_status(purchase_id: int, status: str) -> str:
        """Update a purchase status. Values: approved, completed, rejected, cancelled."""
        db_path = server.BASE_DIR / "data" / "spending.db"
        result = _update_status(str(db_path), purchase_id, status)
        return json.dumps(result, default=str)

    @mcp.tool
    def purchasing_get_summary(period: str = "today") -> str:
        """Get spending summary. period: 'today', 'week', or 'month'."""
        db_path = server.BASE_DIR / "data" / "spending.db"
        result = _get_summary(str(db_path), period)
        return json.dumps(result)
