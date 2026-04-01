import logging
import time

import requests

logger = logging.getLogger(__name__)


class NetoAdapter:
    def __init__(self, url: str, username: str, api_key: str):
        self.endpoint = f"{url.rstrip('/')}/do/WS/NetoAPI"
        self.username = username
        self.api_key = api_key

    def _request(self, action: str, body: dict, retries: int = 3) -> dict:
        headers = {
            "NETOAPI_ACTION": action,
            "NETOAPI_USERNAME": self.username,
            "NETOAPI_KEY": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        delay = 2
        last_exception = None
        for attempt in range(retries):
            try:
                response = requests.post(
                    self.endpoint, json=body, headers=headers, timeout=30
                )
                if response.status_code in (429, 502, 503, 504):
                    if attempt < retries - 1:
                        logger.warning(
                            "Neto API %s returned %d, retrying in %ds (attempt %d/%d)",
                            action,
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
                        "Neto API %s request error: %s, retrying in %ds",
                        action,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
        if last_exception:
            raise last_exception
        return {}

    # -------------------------------------------------------------------------
    # Product methods
    # -------------------------------------------------------------------------

    def add_item(
        self,
        sku,
        name,
        price,
        description="",
        brand="",
        model="",
        cost_price=None,
        images=None,
        **kwargs,
    ) -> dict:
        item = {
            "SKU": sku,
            "Name": name,
            "DefaultPrice": price,
            "Description": description,
            "Brand": brand,
            "Model": model,
            "IsInventoried": True,
            "Visible": True,
            "IsActive": True,
            "Approved": True,
        }
        if cost_price is not None:
            item["CostPrice"] = cost_price
        if images is not None:
            item["Images"] = {"Image": images}
        item.update(kwargs)
        return self._request("AddItem", {"Item": [item]})

    def get_item(self, sku, output_fields=None) -> dict:
        if output_fields is None:
            output_fields = [
                "ParentSKU",
                "ID",
                "Brand",
                "Model",
                "Name",
                "Description",
                "DefaultPrice",
                "CostPrice",
                "AvailableSellQuantity",
                "WarehouseQuantity",
                "Images",
                "Categories",
                "DateUpdated",
            ]
        return self._request(
            "GetItem",
            {"Filter": {"SKU": [sku], "OutputSelector": output_fields}},
        )

    def get_items(
        self,
        is_active=None,
        limit=50,
        page=0,
        date_updated_from=None,
        output_fields=None,
    ) -> dict:
        if output_fields is None:
            output_fields = [
                "ParentSKU",
                "ID",
                "Brand",
                "Model",
                "Name",
                "DefaultPrice",
                "CostPrice",
                "AvailableSellQuantity",
                "Images",
                "Categories",
                "DateUpdated",
            ]
        filter_params = {
            "Limit": limit,
            "Page": page,
            "OrderBy": "DateUpdated",
            "OrderDirection": "DESC",
            "OutputSelector": output_fields,
        }
        if is_active is not None:
            filter_params["IsActive"] = is_active
        if date_updated_from is not None:
            filter_params["DateUpdatedFrom"] = date_updated_from
        return self._request("GetItem", {"Filter": filter_params})

    def update_item(self, sku, **fields) -> dict:
        item = {"SKU": sku}
        for key, value in fields.items():
            if key == "warehouse_quantity":
                item["WarehouseQuantity"] = value
            elif key == "default_price":
                item["DefaultPrice"] = str(value)
            elif key == "cost_price":
                item["CostPrice"] = str(value)
            elif key == "name":
                item["Name"] = value
            elif key == "description":
                item["Description"] = value
            elif key == "is_active":
                item["IsActive"] = "True" if value else "False"
            elif key == "visible":
                item["Visible"] = "True" if value else "False"
            elif key == "images":
                item["Images"] = {"Image": value}
            elif key == "categories":
                item["Categories"] = {
                    "Category": [{"CategoryID": str(c)} for c in value]
                }
            else:
                item[key] = value
        return self._request("UpdateItem", {"Item": [item]})

    # -------------------------------------------------------------------------
    # Order methods
    # -------------------------------------------------------------------------

    def get_orders(self, status="New", date_from=None, date_to=None) -> dict:
        filter_params = {
            "OrderStatus": status,
            "OutputSelector": [
                "OrderID",
                "OrderStatus",
                "Username",
                "ShipAddress",
                "BillAddress",
                "OrderLine",
                "OrderLine.ShippingTracking",
                "DatePlaced",
                "DateUpdated",
                "GrandTotal",
            ],
        }
        if date_from is not None:
            filter_params["DateFrom"] = date_from
        if date_to is not None:
            filter_params["DateTo"] = date_to
        return self._request("GetOrder", {"Filter": filter_params})

    def update_order(
        self, order_id, status, tracking=None, carrier=None, send_email=None
    ) -> dict:
        order = {"OrderID": order_id, "OrderStatus": status}
        if tracking is not None and carrier is not None:
            order["OrderLine"] = {
                "TrackingDetails": {
                    "ShippingMethod": carrier,
                    "TrackingNumber": tracking,
                }
            }
        if send_email is not None:
            order["SendOrderEmail"] = send_email
        return self._request("UpdateOrder", {"Order": [order]})

    # -------------------------------------------------------------------------
    # RMA methods
    # -------------------------------------------------------------------------

    def add_rma(
        self,
        order_id,
        invoice_number,
        customer_username,
        lines,
        status="Open",
    ) -> dict:
        rma_dict = {
            "OrderID": order_id,
            "InvoiceNumber": invoice_number,
            "CustomerUsername": customer_username,
            "RmaStatus": status,
            "RmaLine": lines,
        }
        return self._request("AddRma", {"Rma": [rma_dict]})

    def get_rmas(self, status=None, date_from=None) -> dict:
        filter_params = {
            "OutputSelector": [
                "RmaID",
                "OrderID",
                "CustomerUsername",
                "RmaStatus",
                "RefundTotal",
                "RmaLine",
                "DateIssued",
            ]
        }
        if status is not None:
            filter_params["RmaStatus"] = status
        if date_from is not None:
            filter_params["DateFrom"] = date_from
        return self._request("GetRma", {"Filter": filter_params})
