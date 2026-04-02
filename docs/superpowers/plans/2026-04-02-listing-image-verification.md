# Listing Image Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MCP tools that fetch Neto product listings with base64-encoded images so Simon can use Claude's vision to verify images match listing titles.

**Architecture:** Two MCP tools (`neto_verify_listing`, `neto_verify_listings`) in a new `tools/verification_tools.py` module. A helper `_download_images` handles HTTP image fetching and base64 encoding. Follows existing singleton/register pattern. No new dependencies.

**Tech Stack:** Python, FastMCP, requests, base64 (stdlib), unittest.mock for tests

---

## File Structure

| File | Responsibility |
|------|---------------|
| `tools/verification_tools.py` | New — MCP tools + image download helper |
| `server.py` | Modify — add import and registration |
| `tests/test_verification.py` | New — unit tests for all verification tools |

---

### Task 1: Image Download Helper — Test + Implementation

**Files:**
- Create: `tests/test_verification.py`
- Create: `tools/verification_tools.py`

- [ ] **Step 1: Write failing tests for `_download_images`**

```python
import base64
import json
from unittest.mock import MagicMock, patch

import pytest


def _mock_image_response(content=b"\x89PNG\r\n", content_type="image/png", status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = content
    mock.headers = {"Content-Type": content_type}
    if status_code >= 400:
        from requests import HTTPError
        mock.raise_for_status.side_effect = HTTPError(f"HTTP {status_code}", response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


class TestDownloadImages:
    def test_downloads_and_encodes_images(self):
        from tools.verification_tools import _download_images

        img_bytes = b"\x89PNG\r\nfake image data"
        mock_resp = _mock_image_response(content=img_bytes, content_type="image/png")

        with patch("requests.get", return_value=mock_resp):
            result = _download_images(["https://cdn.example.com/img1.png"])

        assert len(result) == 1
        assert result[0]["url"] == "https://cdn.example.com/img1.png"
        assert result[0]["base64"] == base64.b64encode(img_bytes).decode("ascii")
        assert result[0]["content_type"] == "image/png"

    def test_failed_download_returns_error(self):
        from tools.verification_tools import _download_images

        from requests import RequestException
        with patch("requests.get", side_effect=RequestException("Connection refused")):
            result = _download_images(["https://cdn.example.com/broken.jpg"])

        assert len(result) == 1
        assert "error" in result[0]
        assert result[0]["url"] == "https://cdn.example.com/broken.jpg"

    def test_max_images_caps_downloads(self):
        from tools.verification_tools import _download_images

        mock_resp = _mock_image_response()
        urls = ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg", "https://cdn.example.com/3.jpg"]

        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = _download_images(urls, max_images=2)

        assert len(result) == 2
        assert mock_get.call_count == 2

    def test_max_images_zero_downloads_all(self):
        from tools.verification_tools import _download_images

        mock_resp = _mock_image_response()
        urls = ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg"]

        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = _download_images(urls, max_images=0)

        assert len(result) == 2
        assert mock_get.call_count == 2

    def test_empty_url_list(self):
        from tools.verification_tools import _download_images

        result = _download_images([])
        assert result == []

    def test_fallback_content_type(self):
        from tools.verification_tools import _download_images

        mock_resp = _mock_image_response(content_type="")
        mock_resp.headers = {}

        with patch("requests.get", return_value=mock_resp):
            result = _download_images(["https://cdn.example.com/img.jpg"])

        assert result[0]["content_type"] == "image/jpeg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest tests/test_verification.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.verification_tools'`

- [ ] **Step 3: Implement `_download_images` in `tools/verification_tools.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest tests/test_verification.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools
git add tools/verification_tools.py tests/test_verification.py
git commit -m "feat: add _download_images helper with tests"
```

---

### Task 2: Single SKU Tool — Test + Implementation

**Files:**
- Modify: `tests/test_verification.py`
- Modify: `tools/verification_tools.py`

- [ ] **Step 1: Write failing tests for `neto_verify_listing`**

Append to `tests/test_verification.py`:

```python
def _mock_neto_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


class TestNetoVerifyListing:
    @patch("tools.verification_tools._get_neto")
    @patch("requests.get")
    def test_returns_product_with_images(self, mock_get, mock_get_neto):
        from tools.verification_tools import _neto_verify_listing

        mock_neto = MagicMock()
        mock_neto.get_item.return_value = {
            "Item": [{
                "SKU": "ML-T480",
                "Name": "Lenovo ThinkPad T480",
                "Description": "14-inch laptop",
                "Brand": "Lenovo",
                "Model": "T480",
                "DefaultPrice": "549.00",
                "Images": {"Image": ["https://cdn.example.com/img1.jpg"]},
            }]
        }
        mock_get_neto.return_value = mock_neto

        img_bytes = b"\xff\xd8\xff\xe0fake jpeg"
        mock_get.return_value = _mock_image_response(content=img_bytes, content_type="image/jpeg")

        result = json.loads(_neto_verify_listing("ML-T480"))

        assert result["sku"] == "ML-T480"
        assert result["name"] == "Lenovo ThinkPad T480"
        assert result["image_count"] == 1
        assert result["images"][0]["content_type"] == "image/jpeg"
        assert result["images"][0]["base64"] == base64.b64encode(img_bytes).decode("ascii")

    @patch("tools.verification_tools._get_neto")
    def test_sku_not_found(self, mock_get_neto):
        from tools.verification_tools import _neto_verify_listing

        mock_neto = MagicMock()
        mock_neto.get_item.return_value = {"Item": []}
        mock_get_neto.return_value = mock_neto

        result = json.loads(_neto_verify_listing("NONEXISTENT"))

        assert result["error"] == "SKU not found in Neto"
        assert result["sku"] == "NONEXISTENT"

    @patch("tools.verification_tools._get_neto")
    def test_product_with_no_images(self, mock_get_neto):
        from tools.verification_tools import _neto_verify_listing

        mock_neto = MagicMock()
        mock_neto.get_item.return_value = {
            "Item": [{
                "SKU": "ML-BARE",
                "Name": "No Image Product",
                "Description": "",
                "Brand": "",
                "Model": "",
                "DefaultPrice": "10.00",
                "Images": {},
            }]
        }
        mock_get_neto.return_value = mock_neto

        result = json.loads(_neto_verify_listing("ML-BARE"))

        assert result["sku"] == "ML-BARE"
        assert result["image_count"] == 0
        assert result["images"] == []

    @patch("tools.verification_tools._get_neto")
    def test_neto_api_error(self, mock_get_neto):
        from tools.verification_tools import _neto_verify_listing

        mock_neto = MagicMock()
        mock_neto.get_item.side_effect = Exception("API timeout")
        mock_get_neto.return_value = mock_neto

        result = json.loads(_neto_verify_listing("ML-T480"))

        assert "error" in result
        assert "Neto API error" in result["error"]

    @patch("tools.verification_tools._get_neto")
    @patch("requests.get")
    def test_max_images_limits_downloads(self, mock_get, mock_get_neto):
        from tools.verification_tools import _neto_verify_listing

        mock_neto = MagicMock()
        mock_neto.get_item.return_value = {
            "Item": [{
                "SKU": "ML-MANY",
                "Name": "Many Images",
                "Description": "",
                "Brand": "",
                "Model": "",
                "DefaultPrice": "99.00",
                "Images": {"Image": [
                    "https://cdn.example.com/1.jpg",
                    "https://cdn.example.com/2.jpg",
                    "https://cdn.example.com/3.jpg",
                ]},
            }]
        }
        mock_get_neto.return_value = mock_neto
        mock_get.return_value = _mock_image_response()

        result = json.loads(_neto_verify_listing("ML-MANY", max_images=1))

        assert result["image_count"] == 1
        assert len(result["images"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest tests/test_verification.py::TestNetoVerifyListing -v`
Expected: FAIL with `cannot import name '_neto_verify_listing'`

- [ ] **Step 3: Implement `_neto_verify_listing` and register tool**

Add to `tools/verification_tools.py`, replacing the `register` function:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest tests/test_verification.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools
git add tools/verification_tools.py tests/test_verification.py
git commit -m "feat: add neto_verify_listing tool with tests"
```

---

### Task 3: Batch Tool — Test + Implementation

**Files:**
- Modify: `tests/test_verification.py`
- Modify: `tools/verification_tools.py`

- [ ] **Step 1: Write failing tests for `neto_verify_listings`**

Append to `tests/test_verification.py`:

```python
class TestNetoVerifyListings:
    @patch("tools.verification_tools._get_neto")
    @patch("requests.get")
    def test_returns_batch_with_summary(self, mock_get, mock_get_neto):
        from tools.verification_tools import _neto_verify_listings

        mock_neto = MagicMock()
        mock_neto.get_items.return_value = {
            "Item": [
                {
                    "SKU": "SKU-001",
                    "Name": "Product One",
                    "Description": "Desc one",
                    "Brand": "Brand1",
                    "Model": "M1",
                    "DefaultPrice": "100.00",
                    "Images": {"Image": ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg"]},
                },
                {
                    "SKU": "SKU-002",
                    "Name": "Product Two",
                    "Description": "Desc two",
                    "Brand": "Brand2",
                    "Model": "M2",
                    "DefaultPrice": "200.00",
                    "Images": {},
                },
            ]
        }
        mock_get_neto.return_value = mock_neto
        mock_get.return_value = _mock_image_response()

        result = json.loads(_neto_verify_listings(limit=20, page=0))

        assert result["product_count"] == 2
        assert result["products_with_images"] == 1
        assert result["products_without_images"] == 1
        assert result["total_images"] == 2
        assert result["page"] == 0
        assert result["limit"] == 20
        assert len(result["products"]) == 2
        assert result["products"][0]["sku"] == "SKU-001"
        assert result["products"][0]["image_count"] == 2
        assert result["products"][1]["image_count"] == 0

    @patch("tools.verification_tools._get_neto")
    def test_neto_api_error_in_batch(self, mock_get_neto):
        from tools.verification_tools import _neto_verify_listings

        mock_neto = MagicMock()
        mock_neto.get_items.side_effect = Exception("API down")
        mock_get_neto.return_value = mock_neto

        result = json.loads(_neto_verify_listings())

        assert "error" in result
        assert "Neto API error" in result["error"]

    @patch("tools.verification_tools._get_neto")
    def test_empty_store(self, mock_get_neto):
        from tools.verification_tools import _neto_verify_listings

        mock_neto = MagicMock()
        mock_neto.get_items.return_value = {"Item": []}
        mock_get_neto.return_value = mock_neto

        result = json.loads(_neto_verify_listings())

        assert result["product_count"] == 0
        assert result["total_images"] == 0
        assert result["products"] == []

    @patch("tools.verification_tools._get_neto")
    @patch("requests.get")
    def test_max_images_applied_per_product(self, mock_get, mock_get_neto):
        from tools.verification_tools import _neto_verify_listings

        mock_neto = MagicMock()
        mock_neto.get_items.return_value = {
            "Item": [{
                "SKU": "SKU-001",
                "Name": "Product",
                "Description": "",
                "Brand": "",
                "Model": "",
                "DefaultPrice": "50.00",
                "Images": {"Image": ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg", "https://cdn.example.com/3.jpg"]},
            }]
        }
        mock_get_neto.return_value = mock_neto
        mock_get.return_value = _mock_image_response()

        result = json.loads(_neto_verify_listings(max_images=1))

        assert result["products"][0]["image_count"] == 1
        assert result["total_images"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest tests/test_verification.py::TestNetoVerifyListings -v`
Expected: FAIL with `cannot import name '_neto_verify_listings'`

- [ ] **Step 3: Implement `_neto_verify_listings` and register tool**

Add to `tools/verification_tools.py` before `register`, and update `register`:

```python
def _neto_verify_listings(limit: int = 20, page: int = 0, max_images: int = 0) -> str:
    try:
        result = _get_neto().get_items(
            limit=limit,
            page=page,
            output_fields=["SKU", "Name", "Description", "Brand", "Model", "DefaultPrice", "Images"],
        )
    except Exception as e:
        return json.dumps({"error": f"Neto API error: {e}"})

    items = result.get("Item", [])
    products = []
    total_images = 0
    with_images = 0
    without_images = 0

    for item in items:
        bundle = _build_product_bundle(item, max_images=max_images)
        products.append(bundle)
        total_images += bundle["image_count"]
        if bundle["image_count"] > 0:
            with_images += 1
        else:
            without_images += 1

    return json.dumps({
        "page": page,
        "limit": limit,
        "product_count": len(products),
        "total_images": total_images,
        "products_with_images": with_images,
        "products_without_images": without_images,
        "products": products,
    }, default=str)


def register(mcp):
    @mcp.tool
    def neto_verify_listing(sku: str, max_images: int = 0) -> str:
        """Fetch a Neto product by SKU with all images as base64 for visual verification. max_images=0 means all images; positive value caps the count."""
        return _neto_verify_listing(sku, max_images=max_images)

    @mcp.tool
    def neto_verify_listings(limit: int = 20, page: int = 0, max_images: int = 0) -> str:
        """Fetch Neto products in batch with all images as base64 for visual verification. Returns summary counts and per-product image bundles."""
        return _neto_verify_listings(limit=limit, page=page, max_images=max_images)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest tests/test_verification.py -v`
Expected: All 15 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools
git add tools/verification_tools.py tests/test_verification.py
git commit -m "feat: add neto_verify_listings batch tool with tests"
```

---

### Task 4: Server Registration + Integration Test

**Files:**
- Modify: `server.py:134-153`

- [ ] **Step 1: Add verification tools registration to `server.py`**

Add after the existing `register_facebook(mcp)` line in `server.py`:

```python
    from tools.verification_tools import register as register_verification
```

And:

```python
    register_verification(mcp)
```

- [ ] **Step 2: Run full test suite**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest -v`
Expected: All tests PASS including existing tests

- [ ] **Step 3: Verify MCP server starts cleanly**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && timeout 5 python3 server.py 2>&1 || true`
Expected: FastMCP banner prints, server starts on stdio transport, no import errors

- [ ] **Step 4: Commit**

```bash
cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools
git add server.py
git commit -m "feat: register verification tools in MCP server"
```

---

### Task 5: Push and Update PR

**Files:** None (git operations only)

- [ ] **Step 1: Run full test suite one final time**

Run: `cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools && python3 -m pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Push to remote**

```bash
cd /mnt/c/Users/User/.openclaw/workspace/david-business-tools
git push origin feature/facebook-marketplace
```

- [ ] **Step 3: Verify PR updated**

Run: `gh pr view 1 --repo rodbland2021/david-business-tools`
Expected: PR shows new commits
