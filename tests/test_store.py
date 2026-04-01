import json
import sqlite3

import pytest
from unittest.mock import MagicMock

from adapters.store import StoreAdapter


def _neto_success(sku="TEST-001"):
    return {
        "Item": [{"SKU": sku}],
        "Messages": {"Error": [], "Warning": []},
    }


@pytest.fixture
def neto():
    mock = MagicMock()
    mock.add_item.return_value = _neto_success()
    mock.update_item.return_value = _neto_success()
    return mock


@pytest.fixture
def store(tmp_path, neto):
    db = str(tmp_path / "test.db")
    adapter = StoreAdapter(db_path=db, neto_adapter=neto)
    adapter.init_db()
    return adapter


class TestStoreAdapter:
    def test_add_product(self, store, neto):
        neto.add_item.return_value = _neto_success("DELL-001")
        result = store.add_product(
            sku="DELL-001",
            name="Dell XPS 15",
            price=1999.99,
            brand="Dell",
            model="XPS 15",
            specs={"ram": "16GB", "cpu": "i7"},
        )
        assert result["sku"] == "DELL-001"
        assert result["name"] == "Dell XPS 15"
        assert result["price"] == 1999.99
        assert result["neto_synced"] is True

        product = store.get_product("DELL-001")
        assert product is not None
        assert product["sku"] == "DELL-001"
        assert product["brand"] == "Dell"
        specs = json.loads(product["specs"])
        assert specs["ram"] == "16GB"
        assert specs["cpu"] == "i7"

    def test_get_product_not_found(self, store):
        result = store.get_product("NONEXISTENT-999")
        assert result is None

    def test_list_products(self, store, neto):
        neto.add_item.return_value = _neto_success("A-001")
        store.add_product(sku="A-001", name="Product Alpha", price=10.00)
        neto.add_item.return_value = _neto_success("B-002")
        store.add_product(sku="B-002", name="Product Beta", price=20.00)

        products = store.list_products()
        assert len(products) == 2
        skus = {p["sku"] for p in products}
        assert skus == {"A-001", "B-002"}

    def test_list_products_filter_brand(self, store, neto):
        neto.add_item.return_value = _neto_success("DELL-001")
        store.add_product(sku="DELL-001", name="Dell Laptop", price=1500.00, brand="Dell")
        neto.add_item.return_value = _neto_success("HP-001")
        store.add_product(sku="HP-001", name="HP Laptop", price=1200.00, brand="HP")

        results = store.list_products(brand="Dell")
        assert len(results) == 1
        assert results[0]["sku"] == "DELL-001"
        assert results[0]["brand"] == "Dell"

    def test_list_products_filter_in_stock(self, store, neto):
        neto.add_item.return_value = _neto_success("IN-STOCK-001")
        store.add_product(sku="IN-STOCK-001", name="In Stock Product", price=50.00, stock=5)
        neto.add_item.return_value = _neto_success("OUT-OF-STOCK-001")
        store.add_product(sku="OUT-OF-STOCK-001", name="Out of Stock Product", price=30.00, stock=0)

        results = store.list_products(in_stock=True)
        assert len(results) == 1
        assert results[0]["sku"] == "IN-STOCK-001"
        assert results[0]["stock"] == 5

    def test_update_product(self, store, neto):
        neto.add_item.return_value = _neto_success("UPD-001")
        store.add_product(sku="UPD-001", name="Original Name", price=99.99)

        neto.update_item.return_value = _neto_success("UPD-001")
        updated = store.update_product("UPD-001", price=149.99)

        assert updated["price"] == 149.99
        # Verify it persisted
        fetched = store.get_product("UPD-001")
        assert fetched["price"] == 149.99

    def test_update_stock(self, store, neto):
        neto.add_item.return_value = _neto_success("STK-001")
        store.add_product(sku="STK-001", name="Stock Test", price=10.00, stock=0)

        neto.update_item.return_value = _neto_success("STK-001")
        updated = store.update_stock("STK-001", 25, action="set")

        assert updated["stock"] == 25
        fetched = store.get_product("STK-001")
        assert fetched["stock"] == 25

    def test_update_stock_increment(self, store, neto):
        neto.add_item.return_value = _neto_success("INC-001")
        store.add_product(sku="INC-001", name="Increment Test", price=10.00, stock=10)

        neto.update_item.return_value = _neto_success("INC-001")
        updated = store.update_stock("INC-001", 3, action="increment")

        assert updated["stock"] == 13

    def test_update_stock_decrement(self, store, neto):
        neto.add_item.return_value = _neto_success("DEC-001")
        store.add_product(sku="DEC-001", name="Decrement Test", price=10.00, stock=10)

        neto.update_item.return_value = _neto_success("DEC-001")
        updated = store.update_stock("DEC-001", 2, action="decrement")

        assert updated["stock"] == 8

    def test_get_sync_status(self, store, tmp_path):
        # Insert a product directly with neto_synced_at=NULL bypassing the adapter
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            INSERT INTO products (sku, name, price, neto_synced_at, updated_at, created_at)
            VALUES ('UNSYNC-001', 'Unsynced Product', 49.99, NULL,
                    datetime('now'), datetime('now'))
            """
        )
        conn.commit()
        conn.close()

        status = store.get_sync_status()
        assert status["total_products"] >= 1
        assert "UNSYNC-001" in status["neto_unsynced"]

    # ------------------------------------------------------------------
    # sync_from_platform tests
    # ------------------------------------------------------------------

    def test_sync_from_platform(self, store, neto):
        """Two items returned by neto.get_items appear in local DB with correct fields."""
        neto.get_items.return_value = {
            "GetItem": {
                "Item": [
                    {
                        "SKU": "SYNC-001",
                        "Name": "Sync Product One",
                        "DefaultPrice": 299.00,
                        "CostPrice": 150.00,
                        "Brand": "Acme",
                        "Model": "M1",
                        "AvailableSellQuantity": "5",
                    },
                    {
                        "SKU": "SYNC-002",
                        "Name": "Sync Product Two",
                        "DefaultPrice": 499.00,
                        "CostPrice": 250.00,
                        "Brand": "Beta",
                        "Model": "M2",
                        "AvailableSellQuantity": "10",
                    },
                ]
            }
        }

        result = store.sync_from_platform()

        assert result["total_fetched"] == 2
        assert result["synced"] == 2

        p1 = store.get_product("SYNC-001")
        assert p1 is not None
        assert p1["name"] == "Sync Product One"
        assert p1["price"] == 299.00
        assert p1["brand"] == "Acme"
        assert p1["stock"] == 5
        assert p1["neto_synced_at"] is not None

        p2 = store.get_product("SYNC-002")
        assert p2 is not None
        assert p2["name"] == "Sync Product Two"
        assert p2["price"] == 499.00
        assert p2["stock"] == 10
        assert p2["neto_synced_at"] is not None

    def test_sync_from_platform_incremental(self, store, neto, tmp_path):
        """sync_from_platform passes the stored neto_synced_at as date_updated_from."""
        last_sync_time = "2026-03-01 12:00:00"

        # Insert a product that was already synced at a known time
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            INSERT INTO products (sku, name, price, neto_synced_at, created_at, updated_at)
            VALUES ('OLD-001', 'Old Product', 99.99, ?, datetime('now'), datetime('now'))
            """,
            (last_sync_time,),
        )
        conn.commit()
        conn.close()

        neto.get_items.return_value = {"GetItem": {"Item": []}}

        store.sync_from_platform()

        call_kwargs = neto.get_items.call_args
        assert call_kwargs is not None
        # date_updated_from should equal the stored neto_synced_at (MAX value)
        assert call_kwargs.kwargs.get("date_updated_from") == last_sync_time or \
               (call_kwargs.args and last_sync_time in call_kwargs.args)

    # ------------------------------------------------------------------
    # sync_to_platform tests
    # ------------------------------------------------------------------

    def test_sync_to_platform_unsynced(self, store, neto, tmp_path):
        """Unsynced product (neto_synced_at=NULL) triggers add_item and gets timestamp set."""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            INSERT INTO products (sku, name, price, neto_synced_at, created_at, updated_at)
            VALUES ('UNSENT-001', 'Unsent Product', 79.99, NULL, datetime('now'), datetime('now'))
            """
        )
        conn.commit()
        conn.close()

        result = store.sync_to_platform()

        neto.add_item.assert_called_once()
        call_kwargs = neto.add_item.call_args
        assert call_kwargs.kwargs.get("sku") == "UNSENT-001" or \
               (call_kwargs.args and "UNSENT-001" in call_kwargs.args)

        assert "UNSENT-001" in result["synced"]
        assert result["failed"] == []

        # Verify neto_synced_at is now set in DB
        p = store.get_product("UNSENT-001")
        assert p["neto_synced_at"] is not None

    def test_sync_to_platform_retry_failed(self, store, neto, tmp_path):
        """When add_item fails for first product and succeeds for second, results reflect 1+1."""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executemany(
            """
            INSERT INTO products (sku, name, price, neto_synced_at, created_at, updated_at)
            VALUES (?, ?, ?, NULL, datetime('now'), datetime('now'))
            """,
            [
                ("FAIL-001", "Failing Product", 50.00),
                ("OK-002", "OK Product", 60.00),
            ],
        )
        conn.commit()
        conn.close()

        # First call raises, second succeeds
        neto.add_item.side_effect = [
            Exception("Neto API error"),
            _neto_success("OK-002"),
        ]

        result = store.sync_to_platform()

        assert len(result["synced"]) == 1
        assert len(result["failed"]) == 1
        failed_skus = [f["sku"] for f in result["failed"]]
        assert "FAIL-001" in failed_skus
        assert "OK-002" in result["synced"]

    def test_sync_to_platform_specific_sku(self, store, neto):
        """Calling sync_to_platform(sku=X) on an already-synced product calls update_item, not add_item."""
        # Add product through normal path so neto_synced_at gets set
        neto.add_item.return_value = _neto_success("THAT-SKU")
        store.add_product(
            sku="THAT-SKU",
            name="That Product",
            price=199.99,
            brand="Gamma",
            description="A fine product",
        )

        # Confirm it's synced
        p = store.get_product("THAT-SKU")
        assert p["neto_synced_at"] is not None

        # Reset mock call counts
        neto.add_item.reset_mock()
        neto.update_item.reset_mock()

        result = store.sync_to_platform(sku="THAT-SKU")

        neto.add_item.assert_not_called()
        neto.update_item.assert_called_once()
        assert "THAT-SKU" in result["synced"]
