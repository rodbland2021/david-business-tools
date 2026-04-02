# Listing Image Verification — Design Spec

## Purpose

Add MCP tools that let Simon (OpenClaw agent) audit Neto product listings by fetching listing data and associated images, returning everything needed for Simon to use Claude's built-in vision to verify images match their listing titles and descriptions.

## Scope

- Neto only (can be extended to Facebook/Kogan later)
- No image analysis logic in the MCP server — Simon's vision handles all verification
- No new dependencies beyond what's already installed (`requests`)

## New File: `tools/verification_tools.py`

### Tools

**`neto_verify_listing(sku: str, max_images: int = 0) -> str`**

Single-product audit. Fetches one product from Neto by SKU, downloads all associated images, returns a JSON bundle with product metadata and base64-encoded images. `max_images=0` means all images; any positive value caps the number downloaded.

**`neto_verify_listings(limit: int = 20, page: int = 0, max_images: int = 0) -> str`**

Batch audit. Fetches multiple products from Neto, downloads all images for each, returns an array of product bundles. Supports pagination. `max_images` caps images per product to control response size.

### Internal Helper

**`_download_images(image_urls: list, max_images: int = 0) -> list[dict]`**

- If `max_images > 0`, truncates the URL list to that count before downloading
- Downloads each image URL with `requests.get(url, timeout=15)`
- Base64-encodes the response body
- Detects content type from response `Content-Type` header (fallback: `image/jpeg`)
- On failure: logs warning, returns `{"url": "...", "error": "download failed: <reason>"}` instead of skipping
- No retry logic (CDN URLs, not rate-limited APIs)
- Logs total download time at INFO level for performance visibility

### Module Pattern

Follows existing tool module conventions:
- Module-level singleton: `_neto = None`
- Lazy initialiser: `_get_neto()` reads config via `server.load_config()`
- `register(mcp)` function decorates tools with `@mcp.tool`
- All returns are `json.dumps(..., default=str)`

## Error Handling

- **SKU not found:** return `{"error": "SKU not found in Neto", "sku": "<sku>"}`
- **Neto API failure:** return `{"error": "Neto API error: <message>"}`
- **Product has no images:** include in results with `"image_count": 0, "images": []`

## Response Format

### Single SKU

```json
{
  "sku": "ML-T480",
  "name": "Lenovo ThinkPad T480",
  "description": "14-inch business laptop...",
  "brand": "Lenovo",
  "model": "T480",
  "price": "549.00",
  "image_count": 3,
  "images": [
    {"url": "https://...", "base64": "/9j/4AAQ...", "content_type": "image/jpeg"},
    {"url": "https://...", "base64": "iVBORw0K...", "content_type": "image/png"},
    {"url": "https://...", "error": "download failed: 404"}
  ]
}
```

### Batch

```json
{
  "page": 0,
  "limit": 20,
  "product_count": 15,
  "total_images": 47,
  "products_with_images": 12,
  "products_without_images": 3,
  "products": [
    { "sku": "...", "name": "...", "image_count": 3, "images": [...] },
    { "sku": "...", "name": "...", "image_count": 0, "images": [] }
  ]
}
```

## Integration

- New import in `server.py`:
  ```python
  from tools.verification_tools import register as register_verification
  register_verification(mcp)
  ```
- No database changes
- No config changes
- No new dependencies

## Testing

- `tests/test_verification.py` — unit tests covering:
  - Single SKU: valid product with images, product with no images, SKU not found
  - Batch: multiple products, pagination, `max_images` cap
  - Image download: successful download, failed download (error in response), timeout
  - Mock Neto API responses and image HTTP requests

## Files Changed

| File | Change |
|------|--------|
| `tools/verification_tools.py` | New file — two MCP tools + image download helper |
| `server.py` | Add import and registration call |
| `tests/test_verification.py` | New file — unit tests |
