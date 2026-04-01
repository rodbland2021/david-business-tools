import json

import server
from adapters.neto import NetoAdapter

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


def register(mcp):
    @mcp.tool
    def neto_get_orders(
        status: str = "New",
        date_from: str = "",
        date_to: str = "",
    ) -> str:
        """Fetch orders from Neto by status. Status values: New, Pick, Pack, Dispatched, Cancelled."""
        result = _get_neto().get_orders(
            status=status,
            date_from=date_from or None,
            date_to=date_to or None,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def neto_update_order(
        order_id: str,
        status: str,
        tracking: str = "",
        carrier: str = "",
        send_email: str = "",
    ) -> str:
        """Update a Neto order. For dispatch: status='Dispatched', provide tracking + carrier. send_email: 'tracking' to notify customer."""
        result = _get_neto().update_order(
            order_id=order_id,
            status=status,
            tracking=tracking or None,
            carrier=carrier or None,
            send_email=send_email or None,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def neto_create_rma(
        order_id: str,
        invoice_number: str,
        customer_username: str,
        sku: str,
        quantity: int = 1,
        reason: str = "",
        resolution: str = "Refund",
        refund_amount: float = 0,
    ) -> str:
        """Create a return (RMA) in Neto for a specific order line."""
        lines = [{
            "SKU": sku,
            "Quantity": quantity,
            "Reason": reason or "",
            "Resolution": resolution,
            "RefundAmount": refund_amount,
        }]
        result = _get_neto().add_rma(
            order_id=order_id,
            invoice_number=invoice_number,
            customer_username=customer_username,
            lines=lines,
        )
        return json.dumps(result, default=str)

    @mcp.tool
    def neto_get_rmas(
        status: str = "",
        date_from: str = "",
    ) -> str:
        """Fetch returns (RMAs) from Neto. Optional status filter: Open, Closed."""
        result = _get_neto().get_rmas(
            status=status or None,
            date_from=date_from or None,
        )
        return json.dumps(result, default=str)
