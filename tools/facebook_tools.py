import json

import server
from adapters.facebook import FacebookMarketplaceAdapter
from adapters.store import StoreAdapter
from adapters.neto import NetoAdapter

_facebook = None
_store = None


def _get_facebook():
    global _facebook
    if _facebook is not None:
        return _facebook
    config = server.load_config()
    fb_cfg = config["facebook"]
    _facebook = FacebookMarketplaceAdapter(
        page_id=fb_cfg["page_id"],
        page_access_token=fb_cfg["page_access_token"],
    )
    return _facebook


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
    def facebook_create_listing(
        sku: str,
        title: str = "",
        price: float = None,
        description: str = "",
        condition: str = "used - like new",
        images_json: str = "[]",
        category: str = "",
        location_json: str = "",
    ) -> str:
        """Create a Facebook Marketplace listing. Pulls product data from local store DB by SKU and posts to Facebook. Override title/price/description if provided, otherwise uses store values. images_json: JSON array of image URLs. location_json: JSON object with latitude/longitude."""
        product = _get_store().get_product(sku)
        if product is None:
            return json.dumps({"error": f"Product {sku} not found in local store"})
        listing_title = title or product.get("name", sku)
        listing_price = price if price is not None else product.get("price", 0)
        listing_desc = description or product.get("description", "")
        listing_condition = condition or product.get("condition", "used - like new")
        images = json.loads(images_json) if images_json else []
        if not images and product.get("images"):
            stored_images = product["images"]
            if isinstance(stored_images, str):
                stored_images = json.loads(stored_images)
            if isinstance(stored_images, list):
                images = stored_images
        location = json.loads(location_json) if location_json else None
        result = _get_facebook().create_listing(
            title=listing_title,
            price=listing_price,
            description=listing_desc,
            condition=listing_condition,
            images=images,
            category=category,
            location=location,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def facebook_update_listing(
        listing_id: str,
        title: str = "",
        price: float = None,
        description: str = "",
        condition: str = "",
        availability: str = "",
        images_json: str = "",
    ) -> str:
        """Update a Facebook Marketplace listing. Only provided fields are changed."""
        fields = {}
        if title:
            fields["title"] = title
        if price is not None:
            fields["price"] = price
        if description:
            fields["description"] = description
        if condition:
            fields["condition"] = condition
        if availability:
            fields["availability"] = availability
        if images_json:
            fields["images"] = json.loads(images_json)
        result = _get_facebook().update_listing(listing_id, **fields)
        return json.dumps(result, default=str)

    @mcp.tool
    def facebook_delete_listing(listing_id: str) -> str:
        """Delete a Facebook Marketplace listing (mark as sold/remove)."""
        result = _get_facebook().delete_listing(listing_id)
        return json.dumps(result, default=str)

    @mcp.tool
    def facebook_list_listings(limit: int = 50) -> str:
        """List all active Facebook Marketplace listings for the page."""
        result = _get_facebook().list_listings(limit=limit)
        return json.dumps(result, default=str)

    @mcp.tool
    def facebook_sync_from_neto(
        sku: str,
        condition: str = "used - like new",
        category: str = "",
        location_json: str = "",
    ) -> str:
        """Fetch a product from Neto by SKU and auto-create a Facebook Marketplace listing from it. location_json: optional JSON object with latitude/longitude."""
        config = server.load_config()
        neto_cfg = config.get("neto", {})
        if not (neto_cfg.get("url") and neto_cfg.get("username") and neto_cfg.get("api_key")):
            return json.dumps({"error": "Neto not configured"})
        neto = NetoAdapter(
            url=neto_cfg["url"],
            username=neto_cfg["username"],
            api_key=neto_cfg["api_key"],
        )
        neto_result = neto.get_item(sku)
        items = neto_result.get("Item", [])
        if not items:
            return json.dumps({"error": f"SKU {sku} not found in Neto"})
        item = items[0]
        images = []
        neto_images = item.get("Images", {})
        if isinstance(neto_images, dict):
            img_list = neto_images.get("Image", [])
            if isinstance(img_list, list):
                images = img_list
            elif isinstance(img_list, str):
                images = [img_list]
        location = json.loads(location_json) if location_json else None
        result = _get_facebook().create_listing(
            title=item.get("Name", sku),
            price=float(item.get("DefaultPrice", 0)),
            description=item.get("Description", ""),
            condition=condition,
            images=images,
            category=category,
            location=location,
        )
        result["_synced_from"] = {
            "sku": sku,
            "neto_name": item.get("Name"),
            "neto_price": item.get("DefaultPrice"),
        }
        return json.dumps(result, default=str)
