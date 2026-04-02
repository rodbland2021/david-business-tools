import logging
import time

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

RETRYABLE_STATUS_CODES = (429, 502, 503, 504)

CONDITION_MAP = {
    "new": "NEW",
    "used - like new": "USED_LIKE_NEW",
    "used - good": "USED_GOOD",
    "used - fair": "USED_FAIR",
    "refurbished": "REFURBISHED",
}


class FacebookMarketplaceAdapter:
    def __init__(self, page_id: str, page_access_token: str):
        self.page_id = page_id
        self.access_token = page_access_token

    # -------------------------------------------------------------------------
    # Internal HTTP helpers
    # -------------------------------------------------------------------------

    def _get(self, path: str, params=None, retries: int = 3) -> dict:
        url = f"{GRAPH_API_BASE}{path}"
        if params is None:
            params = {}
        params["access_token"] = self.access_token
        delay = 2
        last_exception = None
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, timeout=30)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < retries - 1:
                        logger.warning(
                            "Facebook GET %s returned %d, retrying in %ds (attempt %d/%d)",
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
            except requests.HTTPError:
                raise
            except requests.RequestException as e:
                last_exception = e
                if attempt < retries - 1:
                    logger.warning(
                        "Facebook GET %s network error: %s, retrying in %ds",
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
        url = f"{GRAPH_API_BASE}{path}"
        if body is None:
            body = {}
        body["access_token"] = self.access_token
        delay = 2
        last_exception = None
        for attempt in range(retries):
            try:
                response = requests.post(url, json=body, timeout=30)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < retries - 1:
                        logger.warning(
                            "Facebook POST %s returned %d, retrying in %ds (attempt %d/%d)",
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
            except requests.HTTPError:
                raise
            except requests.RequestException as e:
                last_exception = e
                if attempt < retries - 1:
                    logger.warning(
                        "Facebook POST %s network error: %s, retrying in %ds",
                        path,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
        if last_exception:
            raise last_exception
        return {}

    def _delete(self, path: str, retries: int = 3) -> dict:
        url = f"{GRAPH_API_BASE}{path}"
        params = {"access_token": self.access_token}
        delay = 2
        last_exception = None
        for attempt in range(retries):
            try:
                response = requests.delete(url, params=params, timeout=30)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < retries - 1:
                        logger.warning(
                            "Facebook DELETE %s returned %d, retrying in %ds (attempt %d/%d)",
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
            except requests.HTTPError:
                raise
            except requests.RequestException as e:
                last_exception = e
                if attempt < retries - 1:
                    logger.warning(
                        "Facebook DELETE %s network error: %s, retrying in %ds",
                        path,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
        if last_exception:
            raise last_exception
        return {}

    # -------------------------------------------------------------------------
    # Listing methods
    # -------------------------------------------------------------------------

    def create_listing(
        self,
        title: str,
        price: float,
        description: str = "",
        condition: str = "new",
        images: list = None,
        category: str = "",
        location: dict = None,
        currency: str = "AUD",
    ) -> dict:
        body = {
            "name": title,
            "price": int(price * 100),
            "currency": currency,
            "description": description,
            "condition": CONDITION_MAP.get(condition.lower(), condition.upper()),
            "availability": "IN_STOCK",
        }
        if category:
            body["category"] = category
        if images:
            body["images"] = [{"url": url} for url in images]
        if location:
            body["location"] = location
        return self._post(f"/{self.page_id}/commerce_listings", body=body)

    def update_listing(self, listing_id: str, **fields) -> dict:
        body = {}
        if "title" in fields:
            body["name"] = fields["title"]
        if "price" in fields:
            body["price"] = int(fields["price"] * 100)
        if "description" in fields:
            body["description"] = fields["description"]
        if "condition" in fields:
            body["condition"] = CONDITION_MAP.get(
                fields["condition"].lower(), fields["condition"].upper()
            )
        if "images" in fields:
            body["images"] = [{"url": url} for url in fields["images"]]
        if "availability" in fields:
            body["availability"] = fields["availability"]
        if "currency" in fields:
            body["currency"] = fields["currency"]
        return self._post(f"/{listing_id}", body=body)

    def delete_listing(self, listing_id: str) -> dict:
        return self._delete(f"/{listing_id}")

    def get_listing(self, listing_id: str) -> dict:
        fields = "id,name,price,currency,description,condition,availability,images,created_time,updated_time"
        return self._get(f"/{listing_id}", params={"fields": fields})

    def list_listings(self, limit: int = 50) -> dict:
        fields = "id,name,price,currency,description,condition,availability,images,created_time"
        return self._get(
            f"/{self.page_id}/commerce_listings",
            params={"fields": fields, "limit": limit},
        )
