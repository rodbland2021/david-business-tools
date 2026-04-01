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

## Tools (30)

**Store** (8): add/get/list/update products, update stock, sync to/from platform, check sync status

**Neto Orders** (4): get orders, update order, create RMA, get RMAs

**Kogan** (8): get/fulfill/cancel/refund orders, create product, update stock/price, get categories

**Gmail** (4): get unread, read message, create draft, send draft

**Purchasing** (4): check limits, log purchase, update status, get summary

**Specs** (2): generate PowerShell script, parse script output

## Laptop Spec Extraction

Run `scripts/extract_specs.ps1` on a Windows laptop to get hardware specs as JSON. Paste the output into the `specs_parse_script_output` tool.
