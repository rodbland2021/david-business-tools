# David Business Tools — MCP Server

Business automation tools for an electronics/tech resale operation. Exposes product management, order processing, email drafting, and purchasing controls as MCP tools.

## Quick Start

1. Copy `config.example.json` to `config.json` and fill in your credentials
2. Install: `pip install -r requirements.txt`
3. Run: `python server.py`

## Use with Claude Code

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "david-business-tools": {
      "command": "python3",
      "args": ["/path/to/david-business-tools/server.py"]
    }
  }
}
```

## Tools (37)

**Store** (8): add/get/list/update products, update stock, sync to/from platform, check sync status

**Neto Orders** (4): get orders, update order, create RMA, get RMAs

**Kogan** (8): get/fulfill/cancel/refund orders, create product, update stock/price, get categories

**Gmail** (4): get unread, read message, create draft, send draft

**Purchasing** (4): check limits, log purchase, update status, get summary

**Specs** (2): generate PowerShell script, parse script output

**Facebook Marketplace** (5): create/update/delete listings, list all listings, sync from Neto

**Verification** (2): visual audit of product listing images (see below)

## Image Verification — Agent Workflow

Two tools for auditing whether product images match their listing titles and descriptions. Designed for AI agents with vision capabilities.

### Tools

- **`neto_verify_listing(sku, max_images=10)`** — Fetch a single product by SKU with images as base64. Use to spot-check individual listings.
- **`neto_verify_listings(limit=20, page=0, max_images=10)`** — Fetch a batch of products with images. Use `page` to paginate through the full catalogue.

### How to Run an Audit

1. **Scan in batches of 20:**
   - `neto_verify_listings(limit=20, page=0)` — first 20 products
   - `neto_verify_listings(limit=20, page=1)` — next 20 products
   - Continue incrementing `page` until `product_count` returns 0
2. **For each product**, visually inspect the images against the listing title, brand, and description
3. **Flag mismatches** where the image shows: wrong product, wrong brand, placeholder/stock photo, unrelated content, or missing images
4. **Report** with SKU, listing name, and what the image actually shows vs what was expected

### Response Format

Each product in the response includes:
- `sku`, `name`, `description`, `brand`, `model`, `price` — listing metadata
- `image_count` — number of images returned
- `images` — array of `{"url", "status", "base64", "content_type"}` (or `{"url", "status", "error"}` on failure)

Batch responses also include: `product_count`, `total_images`, `products_with_images`, `products_without_images`

### Parameters

- `max_images` — caps image downloads per product (default: 10, set to 0 for all images)
- `limit` — products per batch (default: 20)
- `page` — pagination offset (default: 0)

## Laptop Spec Extraction

Run `scripts/extract_specs.ps1` on a Windows laptop to get hardware specs as JSON. Paste the output into the `specs_parse_script_output` tool.
