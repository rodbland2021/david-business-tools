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
