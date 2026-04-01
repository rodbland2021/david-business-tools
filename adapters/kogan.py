import logging
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

BASE_URLS = {
    "production": "https://nimda.kogan.com/api/marketplace/v2",
    "uat": "https://nimda-marketplace.aws.kgn.io/api/marketplace/v2",
}


class KoganAdapter:
    def __init__(self, seller_id: str, seller_token: str, environment: str = "production"):
        self.base_url = BASE_URLS[environment].rstrip("/")
        self.headers = {
            "SellerToken": seller_token,
            "SellerID": seller_id,
            "Content-Type": "application/json",
        }

    # -------------------------------------------------------------------------
    # Internal HTTP helpers
    # -------------------------------------------------------------------------

    def _get(self, path: str, params=None, retries: int = 3) -> dict:
        url = f"{self.base_url}{path}"
        delay = 2
        last_exception = None
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                if response.status_code in (429, 502, 503, 504):
                    if attempt < retries - 1:
                        logger.warning(
                            "Kogan GET %s returned %d, retrying in %ds (attempt %d/%d)",
                            path,
                            response.status_code,
                            delay,
                            attempt + 1,
                            retries,
                        )
                        time.sleep(delay)
                        delay *= 2
                        continue
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                last_exception = e
                if attempt < retries - 1:
                    logger.warning(
                        "Kogan GET %s request error: %s, retrying in %ds",
                        path,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
        if last_exception:
            raise last_exception
        return {}

    def _post(self, path: str, body=None, retries: int = 3) -> dict:
        url = f"{self.base_url}{path}"
        delay = 2
        last_exception = None
        for attempt in range(retries):
            try:
                response = requests.post(url, headers=self.headers, json=body, timeout=30)
                if response.status_code in (429, 502, 503, 504):
                    if attempt < retries - 1:
                        logger.warning(
                            "Kogan POST %s returned %d, retrying in %ds (attempt %d/%d)",
                            path,
                            response.status_code,
                            delay,
                            attempt + 1,
                            retries,
                        )
                        time.sleep(delay)
                        delay *= 2
                        continue
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                last_exception = e
                if attempt < retries - 1:
                    logger.warning(
                        "Kogan POST %s request error: %s, retrying in %ds",
                        path,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
        if last_exception:
            raise last_exception
        return {}

    def _patch(self, path: str, body=None) -> dict:
        url = f"{self.base_url}{path}"
        response = requests.patch(url, headers=self.headers, json=body, timeout=30)
        response.raise_for_status()
        return response.json()

    def _poll_task(self, pending_url: str, max_wait: int = 300) -> dict:
        elapsed = 0
        delay = 2
        while elapsed < max_wait:
            time.sleep(delay)
            elapsed += delay
            result = self._get_url(pending_url)
            status = result.get("status", result.get("Status", ""))
            if status != "AsyncResponsePending":
                return result
            if delay < 5:
                delay = 5
        return {"error": "timeout", "message": f"Task did not complete within {max_wait}s"}

    def _get_url(self, url: str) -> dict:
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def _resolve_async(self, result: dict) -> dict:
        status = result.get("status", result.get("Status", ""))
        if status == "AsyncResponsePending":
            pending_url = result.get("pending_url") or result.get("PendingUrl") or result.get("url") or result.get("Url")
            if pending_url:
                return self._poll_task(pending_url)
        return result

    # -------------------------------------------------------------------------
    # Product methods
    # -------------------------------------------------------------------------

    def create_product(
        self,
        sku: str,
        title: str,
        description: str,
        brand: str,
        category: str,
        price: float,
        images: list,
        shipping: float = 0.00,
        handling_days: int = 2,
    ) -> dict:
        body = {
            "sku": sku,
            "title": title,
            "description": description,
            "brand": brand,
            "category": category,
            "offer_data": {
                "price": price,
                "shipping": shipping,
                "handling_days": handling_days,
            },
            "images": images,
        }
        result = self._post("/products/", body=body)
        return self._resolve_async(result)

    def update_product(self, sku: str, **fields) -> dict:
        body = {"sku": sku}
        body.update(fields)
        result = self._patch("/products/", body=body)
        return self._resolve_async(result)

    def update_stock_price(self, sku: str, stock=None, price=None) -> dict:
        offer_data = {}
        if stock is not None:
            offer_data["stock"] = stock
        if price is not None:
            offer_data["price"] = price
        body = {
            "sku": sku,
            "offer_data": offer_data,
        }
        result = self._post("/products/stockprice/", body=body)
        return self._resolve_async(result)

    def list_products(
        self,
        search=None,
        sku=None,
        enabled=None,
        brand=None,
        detail: bool = True,
        size: int = 50,
    ) -> dict:
        params = {"size": size}
        if search is not None:
            params["search"] = search
        if sku is not None:
            params["sku"] = sku
        if enabled is not None:
            params["enabled"] = enabled
        if brand is not None:
            params["brand"] = brand
        if detail:
            params["detail"] = True
        return self._get("/products/", params=params)

    # -------------------------------------------------------------------------
    # Order methods
    # -------------------------------------------------------------------------

    def get_orders(self, status: str = "ReleasedForShipment") -> dict:
        return self._get("/orders/", params={"status": status})

    def get_order(self, order_ref: str) -> dict:
        return self._get(f"/orders/{order_ref}/")

    def fulfill_order(self, order_ref: str, items: list) -> dict:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        order_items = []
        for item in items:
            entry = {
                "order_item_id": item.get("order_item_id", ""),
                "sku": item["sku"],
                "quantity": item["quantity"],
                "tracking": item["tracking"],
                "carrier": item["carrier"],
                "shipped_date": item.get("shipped_date", now_utc),
            }
            order_items.append(entry)
        body = {
            "order_ref": order_ref,
            "items": order_items,
        }
        return self._post("/orders/fulfill/", body=body)

    def cancel_order(self, order_ref: str, items: list) -> dict:
        body = {"items": items}
        return self._post(f"/orders/{order_ref}/cancel/", body=body)

    def refund_order(self, order_ref: str, items: list) -> dict:
        body = {"items": items}
        return self._post(f"/orders/{order_ref}/refund/", body=body)

    # -------------------------------------------------------------------------
    # Categories
    # -------------------------------------------------------------------------

    def get_categories(self, store_code=None) -> dict:
        params = {}
        if store_code is not None:
            params["store_code"] = store_code
        return self._get("/categories/", params=params or None)
