import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StoreAdapter:
    def __init__(self, db_path: str, neto_adapter=None):
        self.db_path = db_path
        self.neto = neto_adapter

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self._get_conn()
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

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def add_product(
        self,
        sku,
        name,
        price,
        brand="",
        model="",
        description="",
        specs=None,
        cost_price=None,
        stock=0,
        condition="",
        category="",
        images=None,
    ) -> dict:
        specs_str = json.dumps(specs) if specs is not None else None
        images_str = json.dumps(images) if images is not None else None
        now = self._now()

        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO products
                (sku, name, price, brand, model, description, specs, cost_price,
                 stock, condition, category, images, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sku, name, price, brand, model, description, specs_str,
                cost_price, stock, condition, category, images_str, now, now,
            ),
        )
        conn.commit()
        conn.close()

        neto_synced = False
        if self.neto is not None:
            try:
                result = self.neto.add_item(
                    sku=sku,
                    name=name,
                    price=price,
                    description=description,
                    brand=brand,
                    model=model,
                    cost_price=cost_price,
                    images=images,
                )
                errors = result.get("Messages", {}).get("Error", [])
                if not errors:
                    neto_synced = True
                    sync_time = self._now()
                    conn = self._get_conn()
                    conn.execute(
                        "UPDATE products SET neto_synced_at=? WHERE sku=?",
                        (sync_time, sku),
                    )
                    conn.commit()
                    conn.close()
            except Exception as e:
                logger.error("Failed to sync product %s to Neto: %s", sku, e)

        return {"sku": sku, "name": name, "price": price, "neto_synced": neto_synced}

    def get_product(self, sku) -> dict | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM products WHERE sku=?", (sku,)).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)

    def list_products(
        self,
        search=None,
        brand=None,
        category=None,
        in_stock=None,
    ) -> list[dict]:
        clauses = []
        params = []

        if search is not None:
            clauses.append("(name LIKE ? OR brand LIKE ? OR model LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])

        if brand is not None:
            clauses.append("brand = ?")
            params.append(brand)

        if category is not None:
            clauses.append("category = ?")
            params.append(category)

        if in_stock is True:
            clauses.append("stock > 0")
        elif in_stock is False:
            clauses.append("stock = 0")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM products {where} ORDER BY updated_at DESC"

        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    _UPDATABLE_COLUMNS = frozenset({
        "name", "brand", "model", "description", "specs", "price",
        "cost_price", "stock", "condition", "category", "images",
        "kogan_sku", "kogan_synced_at",
    })

    def update_product(self, sku, **fields) -> dict:
        now = self._now()
        set_parts = ["updated_at=?"]
        params = [now]

        for key, value in fields.items():
            if key not in self._UPDATABLE_COLUMNS:
                raise ValueError(f"Cannot update column: {key}")
            if key in ("specs", "images") and isinstance(value, (dict, list)):
                value = json.dumps(value)
            set_parts.append(f"{key}=?")
            params.append(value)

        params.append(sku)
        sql = f"UPDATE products SET {', '.join(set_parts)} WHERE sku=?"

        conn = self._get_conn()
        conn.execute(sql, params)
        conn.commit()
        conn.close()

        if self.neto is not None:
            neto_fields = {}
            if "price" in fields:
                neto_fields["default_price"] = fields["price"]
            if "name" in fields:
                neto_fields["name"] = fields["name"]
            if "description" in fields:
                neto_fields["description"] = fields["description"]
            if "cost_price" in fields:
                neto_fields["cost_price"] = fields["cost_price"]
            if neto_fields:
                try:
                    self.neto.update_item(sku, **neto_fields)
                except Exception as e:
                    logger.error("Failed to sync update for %s to Neto: %s", sku, e)

        return self.get_product(sku)

    def update_stock(self, sku, quantity, action="set") -> dict:
        now = self._now()
        conn = self._get_conn()

        if action == "set":
            conn.execute(
                "UPDATE products SET stock=?, updated_at=? WHERE sku=?",
                (quantity, now, sku),
            )
        elif action == "increment":
            conn.execute(
                "UPDATE products SET stock=stock+?, updated_at=? WHERE sku=?",
                (quantity, now, sku),
            )
        elif action == "decrement":
            conn.execute(
                "UPDATE products SET stock=MAX(0, stock-?), updated_at=? WHERE sku=?",
                (quantity, now, sku),
            )
        else:
            conn.close()
            raise ValueError(f"Unknown action: {action}")

        conn.commit()
        conn.close()

        if self.neto is not None:
            neto_action = {"set": "Set", "increment": "Increment", "decrement": "Decrement"}[action]
            try:
                self.neto.update_item(
                    sku,
                    warehouse_quantity={
                        "WarehouseID": "1",
                        "Quantity": str(quantity),
                        "Action": neto_action,
                    },
                )
            except Exception as e:
                logger.error("Failed to sync stock for %s to Neto: %s", sku, e)

        return self.get_product(sku)

    def sync_from_platform(self) -> dict:
        if self.neto is None:
            return {"synced": 0, "total_fetched": 0}

        conn = self._get_conn()
        row = conn.execute("SELECT MAX(neto_synced_at) AS last_sync FROM products").fetchone()
        last_sync = row["last_sync"] if row else None
        conn.close()

        result = self.neto.get_items(is_active=True, limit=200, date_updated_from=last_sync)
        items = result.get("GetItem", {}).get("Item", [])
        total_fetched = len(items)
        synced = 0
        now = self._now()

        conn = self._get_conn()
        for item in items:
            sku = item.get("SKU") or item.get("ParentSKU")
            if not sku:
                continue
            name = item.get("Name", "")
            price = item.get("DefaultPrice")
            cost_price = item.get("CostPrice")
            brand = item.get("Brand", "")
            model = item.get("Model", "")
            images_raw = item.get("Images", {})
            images = None
            if isinstance(images_raw, dict):
                images = json.dumps(images_raw.get("Image", []))
            stock = item.get("AvailableSellQuantity", 0)
            try:
                stock = int(stock)
            except (TypeError, ValueError):
                stock = 0

            conn.execute(
                """
                INSERT INTO products
                    (sku, name, price, cost_price, brand, model, images, stock,
                     neto_synced_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET
                    name=excluded.name,
                    price=excluded.price,
                    cost_price=excluded.cost_price,
                    brand=excluded.brand,
                    model=excluded.model,
                    images=excluded.images,
                    stock=excluded.stock,
                    neto_synced_at=excluded.neto_synced_at,
                    updated_at=excluded.updated_at
                """,
                (sku, name, price, cost_price, brand, model, images, stock,
                 now, now, now),
            )
            synced += 1

        conn.commit()
        conn.close()
        return {"synced": synced, "total_fetched": total_fetched}

    def sync_to_platform(self, sku=None) -> dict:
        if self.neto is None:
            return {"synced": [], "failed": []}

        conn = self._get_conn()
        if sku is not None:
            rows = conn.execute("SELECT * FROM products WHERE sku=?", (sku,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM products WHERE neto_synced_at IS NULL"
            ).fetchall()
        conn.close()

        synced = []
        failed = []
        now = self._now()

        for row in rows:
            p = dict(row)
            try:
                if p.get("neto_synced_at") is None:
                    self.neto.add_item(
                        sku=p["sku"],
                        name=p["name"],
                        price=p["price"],
                        description=p.get("description", ""),
                        brand=p.get("brand", ""),
                        model=p.get("model", ""),
                        cost_price=p.get("cost_price"),
                    )
                else:
                    neto_fields = {}
                    if p.get("price") is not None:
                        neto_fields["default_price"] = p["price"]
                    if p.get("name"):
                        neto_fields["name"] = p["name"]
                    if p.get("description"):
                        neto_fields["description"] = p["description"]
                    if p.get("cost_price") is not None:
                        neto_fields["cost_price"] = p["cost_price"]
                    if neto_fields:
                        self.neto.update_item(p["sku"], **neto_fields)

                conn = self._get_conn()
                conn.execute(
                    "UPDATE products SET neto_synced_at=? WHERE sku=?",
                    (now, p["sku"]),
                )
                conn.commit()
                conn.close()
                synced.append(p["sku"])
            except Exception as e:
                logger.error("sync_to_platform failed for %s: %s", p["sku"], e)
                failed.append({"sku": p["sku"], "error": str(e)})

        return {"synced": synced, "failed": failed}

    def get_sync_status(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
        neto_unsynced_rows = conn.execute(
            "SELECT sku FROM products WHERE neto_synced_at IS NULL"
        ).fetchall()
        kogan_unsynced_rows = conn.execute(
            "SELECT sku FROM products WHERE kogan_synced_at IS NULL AND kogan_sku IS NOT NULL"
        ).fetchall()
        conn.close()

        return {
            "total_products": total,
            "neto_unsynced": [r["sku"] for r in neto_unsynced_rows],
            "kogan_unsynced": [r["sku"] for r in kogan_unsynced_rows],
        }
