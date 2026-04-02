import base64
import json
import logging
import time

import requests

import server
from adapters.neto import NetoAdapter

logger = logging.getLogger(__name__)

_neto = None


def _get_neto():
    global _neto
    if _neto is not None:
        return _neto
    config = server.load_config()
    neto_cfg = config["neto"]
    _neto = NetoAdapter(
        url=neto_cfg["url"],
        username=neto_cfg["username"],
        api_key=neto_cfg["api_key"],
    )
    return _neto


def _download_images(image_urls: list, max_images: int = 0) -> list[dict]:
    if max_images > 0:
        image_urls = image_urls[:max_images]

    results = []
    start = time.time()

    for url in image_urls:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            encoded = base64.b64encode(resp.content).decode("ascii")
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if not content_type:
                content_type = "image/jpeg"
            results.append({
                "url": url,
                "base64": encoded,
                "content_type": content_type,
            })
        except Exception as e:
            logger.warning("Failed to download image %s: %s", url, e)
            results.append({
                "url": url,
                "error": f"download failed: {e}",
            })

    elapsed = time.time() - start
    logger.info("Downloaded %d images in %.1fs", len(results), elapsed)

    return results


def _extract_image_urls(item: dict) -> list:
    images = item.get("Images", {})
    if isinstance(images, dict):
        img_list = images.get("Image", [])
        if isinstance(img_list, str):
            return [img_list]
        if isinstance(img_list, list):
            return img_list
    return []


def _build_product_bundle(item: dict, max_images: int = 0) -> dict:
    image_urls = _extract_image_urls(item)
    downloaded = _download_images(image_urls, max_images=max_images)
    return {
        "sku": item.get("SKU", ""),
        "name": item.get("Name", ""),
        "description": item.get("Description", ""),
        "brand": item.get("Brand", ""),
        "model": item.get("Model", ""),
        "price": item.get("DefaultPrice", ""),
        "image_count": len(downloaded),
        "images": downloaded,
    }


def _neto_verify_listing(sku: str, max_images: int = 0) -> str:
    try:
        result = _get_neto().get_item(sku)
    except Exception as e:
        return json.dumps({"error": f"Neto API error: {e}"})

    items = result.get("Item", [])
    if not items:
        return json.dumps({"error": "SKU not found in Neto", "sku": sku})

    bundle = _build_product_bundle(items[0], max_images=max_images)
    return json.dumps(bundle, default=str)


def register(mcp):
    @mcp.tool
    def neto_verify_listing(sku: str, max_images: int = 0) -> str:
        """Fetch a Neto product by SKU with all images as base64 for visual verification. max_images=0 means all images; positive value caps the count."""
        return _neto_verify_listing(sku, max_images=max_images)
