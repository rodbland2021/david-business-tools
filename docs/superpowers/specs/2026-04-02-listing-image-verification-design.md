# Listing Image Verification — Design Spec

## Purpose

Add MCP tools that let Simon (OpenClaw agent) audit Neto product listings by fetching listing data and associated images, returning everything needed for Simon to use Claude's built-in vision to verify images match their listing titles and descriptions.

## Scope

- Neto only (can be extended to Facebook/Kogan later)
- No image analysis logic in the MCP server — Simon's vision handles all verification
- No new dependencies beyond what's already installed (`requests`)

## New File: `tools/verification_tools.py`

### Tools

**`neto_verify_listing(sku: str) -> str`**

Single-product audit. Fetches one product from Neto by SKU, downloads all associated images, returns a JSON bundle with product metadata and base64-encoded images.

**`neto_verify_listings(limit: int = 20, page: int = 0) -> str`**

Batch audit. Fetches multiple products from Neto, downloads all images for each, returns an array of product bundles. Supports pagination.

### Internal Helper

**`_download_images(image_urls: list) -> list[dict]`**

- Downloads each image URL with `requests.get(url, timeout=15)`
- Base64-encodes the response body
- Detects content type from response `Content-Type` header (fallback: `image/jpeg`)
- On failure: logs warning, returns `{"url": "...", "error": "download failed: <reason>"}` instead of skipping
- No retry logic (CDN URLs, not rate-limited APIs)

### Module Pattern

Follows existing tool module conventions:
- Module-level singleton: `_neto = None`
- Lazy initialiser: `_get_neto()` reads config via `server.load_config()`
- `register(mcp)` function decorates tools with `@mcp.tool`
- All returns are `json.dumps(..., default=str)`

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
  "products": [
    { "sku": "...", "name": "...", "image_count": 3, "images": [...] },
    { "sku": "...", "name": "...", "image_count": 1, "images": [...] }
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

## Files Changed

| File | Change |
|------|--------|
| `tools/verification_tools.py` | New file — two MCP tools + image download helper |
| `server.py` | Add import and registration call |
