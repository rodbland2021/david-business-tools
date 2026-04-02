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


def register(mcp):
    pass  # Tools added in subsequent tasks
