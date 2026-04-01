import json

import server
from adapters.kogan import KoganAdapter

_kogan = None


def _get_kogan():
    global _kogan
    if _kogan is not None:
        return _kogan
    config = server.load_config()
    kogan_cfg = config["kogan"]
    _kogan = KoganAdapter(
        seller_id=kogan_cfg["seller_id"],
        seller_token=kogan_cfg["seller_token"],
        environment=kogan_cfg.get("environment", "production"),
    )
    return _kogan


def register(mcp):
    @mcp.tool
    def kogan_get_orders(status: str = "ReleasedForShipment") -> str:
        """Poll for Kogan orders. Default: orders awaiting dispatch."""
        result = _get_kogan().get_orders(status=status)
        return json.dumps(result, default=str)

    @mcp.tool
    def kogan_get_order(order_ref: str) -> str:
        """Get details for a single Kogan order."""
        result = _get_kogan().get_order(order_ref=order_ref)
        return json.dumps(result, default=str)

    @mcp.tool
    def kogan_fulfill_order(order_ref: str, items_json: str) -> str:
        """Dispatch a Kogan order. items_json: JSON array of {sku, quantity, tracking, carrier}."""
        items = json.loads(items_json)
        result = _get_kogan().fulfill_order(order_ref=order_ref, items=items)
        return json.dumps(result, default=str)

    @mcp.tool
    def kogan_cancel_order(order_ref: str, items_json: str) -> str:
        """Cancel a Kogan order. items_json: JSON array of {sku, quantity, reason}. Reasons: ItemNotAvailable, BuyerCanceled, etc."""
        items = json.loads(items_json)
        result = _get_kogan().cancel_order(order_ref=order_ref, items=items)
        return json.dumps(result, default=str)

    @mcp.tool
    def kogan_refund_order(order_ref: str, items_json: str) -> str:
        """Refund a Kogan order. items_json: JSON array of {sku, quantity, reason}. Reasons: Faulty Item, Damage In Transit, etc."""
        items = json.loads(items_json)
        result = _get_kogan().refund_order(order_ref=order_ref, items=items)
        return json.dumps(result, default=str)

    @mcp.tool
    def kogan_create_product(
        sku: str,
        title: str,
        description: str,
        brand: str,
        category: str,
        price: float,
        images_json: str = "[]",
        shipping: float = 0.00,
    ) -> str:
        """Create a new product listing on Kogan. images_json: JSON array of image URLs."""
        images = json.loads(images_json)
        result = _get_kogan().create_product(
            sku=sku,
            title=title,
            description=description,
            brand=brand,
            category=category,
            price=price,
            images=images,
            shipping=shipping,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def kogan_update_stock_price(
        sku: str,
        stock: int = None,
        price: float = None,
    ) -> str:
        """Update stock and/or price for a Kogan product. Higher priority than regular update."""
        result = _get_kogan().update_stock_price(
            sku=sku,
            stock=stock,
            price=price,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def kogan_get_categories(store_code: str = "") -> str:
        """Get Kogan product categories. Optional store_code for non-AU stores."""
        result = _get_kogan().get_categories(
            store_code=store_code or None,
        )
        return json.dumps(result, default=str)
