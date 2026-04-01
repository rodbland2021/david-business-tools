import json

import server
from adapters.store import StoreAdapter
from adapters.neto import NetoAdapter

_store = None


def _get_store():
    global _store
    if _store is not None:
        return _store
    config = server.load_config()
    db_path = server.BASE_DIR / "data" / "products.db"
    neto_cfg = config.get("neto", {})
    neto = None
    if neto_cfg.get("url") and neto_cfg.get("username") and neto_cfg.get("api_key"):
        neto = NetoAdapter(
            url=neto_cfg["url"],
            username=neto_cfg["username"],
            api_key=neto_cfg["api_key"],
        )
    _store = StoreAdapter(db_path=str(db_path), neto_adapter=neto)
    return _store


def register(mcp):
    @mcp.tool
    def store_add_product(
        sku: str,
        name: str,
        price: float,
        brand: str = "",
        model: str = "",
        description: str = "",
        specs: str = "",
        cost_price: float = None,
        stock: int = 0,
        condition: str = "",
        category: str = "",
        images: str = "",
    ) -> str:
        """Add a product to the local database and sync to the ecommerce platform (Neto). specs and images should be JSON strings if provided."""
        parsed_specs = json.loads(specs) if specs else None
        parsed_images = json.loads(images) if images else None
        result = _get_store().add_product(
            sku=sku,
            name=name,
            price=price,
            brand=brand or "",
            model=model or "",
            description=description or "",
            specs=parsed_specs,
            cost_price=cost_price,
            stock=stock,
            condition=condition or "",
            category=category or "",
            images=parsed_images,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def store_get_product(sku: str) -> str:
        """Get a product from the local database by SKU."""
        product = _get_store().get_product(sku)
        if product is None:
            return json.dumps({"error": f"Product {sku} not found"})
        return json.dumps(product, default=str)

    @mcp.tool
    def store_list_products(
        search: str = "",
        brand: str = "",
        category: str = "",
        in_stock: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """List products from the local database with optional filters."""
        in_stock_bool = None
        if in_stock.lower() == "true":
            in_stock_bool = True
        elif in_stock.lower() == "false":
            in_stock_bool = False
        result = _get_store().list_products(
            search=search or None,
            brand=brand or None,
            category=category or None,
            in_stock=in_stock_bool,
            limit=limit,
            offset=offset,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def store_update_product(
        sku: str,
        name: str = "",
        price: float = None,
        description: str = "",
        cost_price: float = None,
    ) -> str:
        """Update a product in the local database and sync changes to Neto."""
        fields = {}
        if name:
            fields["name"] = name
        if price is not None:
            fields["price"] = price
        if description:
            fields["description"] = description
        if cost_price is not None:
            fields["cost_price"] = cost_price
        result = _get_store().update_product(sku, **fields)
        return json.dumps(result, default=str)

    @mcp.tool
    def store_update_stock(sku: str, quantity: int, action: str = "set") -> str:
        """Update stock level for a product. action: 'set', 'increment', or 'decrement'."""
        result = _get_store().update_stock(sku=sku, quantity=quantity, action=action)
        return json.dumps(result, default=str)

    @mcp.tool
    def store_sync_from_platform() -> str:
        """Pull changes from the ecommerce platform (Neto) into the local database. Only fetches products updated since the last sync."""
        result = _get_store().sync_from_platform()
        return json.dumps(result, default=str)

    @mcp.tool
    def store_sync_to_platform(sku: str = "") -> str:
        """Push local products to the ecommerce platform (Neto). If no SKU provided, pushes all pending unsynced products."""
        result = _get_store().sync_to_platform(sku=sku or None)
        return json.dumps(result, default=str)

    @mcp.tool
    def store_get_sync_status() -> str:
        """Check which products are not yet synced to Neto or Kogan."""
        result = _get_store().get_sync_status()
        return json.dumps(result, default=str)
