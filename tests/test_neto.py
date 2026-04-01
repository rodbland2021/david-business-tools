from unittest.mock import MagicMock, patch

import pytest

from adapters.neto import NetoAdapter


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    if status_code >= 400:
        from requests import HTTPError

        mock.raise_for_status.side_effect = HTTPError(
            f"HTTP {status_code}", response=mock
        )
    else:
        mock.raise_for_status.return_value = None
    return mock


@pytest.fixture
def adapter():
    return NetoAdapter(
        url="https://test-store.neto.com.au",
        username="test-user",
        api_key="test-key-123",
    )


class TestNetoAdapter:
    def test_add_item(self, adapter):
        response_data = {"AddItem": {"Item": [{"SKU": "SKU-001", "Result": "Success"}]}}
        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.add_item(
                sku="SKU-001",
                name="Test Product",
                price="29.99",
                description="A test product",
                brand="TestBrand",
            )
        assert result == response_data
        called_headers = mock_post.call_args.kwargs["headers"]
        assert called_headers["NETOAPI_ACTION"] == "AddItem"

    def test_get_item(self, adapter):
        response_data = {
            "GetItem": {
                "Item": [{"SKU": "SKU-001", "Name": "Test Product", "DefaultPrice": "29.99"}]
            }
        }
        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.get_item("SKU-001")
        assert result == response_data
        called_headers = mock_post.call_args.kwargs["headers"]
        assert called_headers["NETOAPI_ACTION"] == "GetItem"

    def test_get_items_with_filters(self, adapter):
        response_data = {
            "GetItem": {
                "Item": [
                    {"SKU": "SKU-001", "Name": "Product One", "DefaultPrice": "19.99"},
                    {"SKU": "SKU-002", "Name": "Product Two", "DefaultPrice": "39.99"},
                ]
            }
        }
        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.get_items(
                is_active="True",
                limit=10,
                page=0,
                date_updated_from="2024-01-01 00:00:00",
            )
        assert result == response_data
        items = result["GetItem"]["Item"]
        assert len(items) == 2
        body = mock_post.call_args.kwargs["json"]
        assert body["Filter"]["IsActive"] == "True"
        assert body["Filter"]["DateUpdatedFrom"] == "2024-01-01 00:00:00"
        assert body["Filter"]["Limit"] == 10

    def test_update_item_stock(self, adapter):
        response_data = {"UpdateItem": {"Item": [{"SKU": "SKU-001", "Result": "Success"}]}}
        warehouse_qty = {"WarehouseID": "1", "Quantity": "50"}
        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.update_item("SKU-001", warehouse_quantity=warehouse_qty)
        assert result == response_data
        called_headers = mock_post.call_args.kwargs["headers"]
        assert called_headers["NETOAPI_ACTION"] == "UpdateItem"
        body = mock_post.call_args.kwargs["json"]
        assert body["Item"][0]["WarehouseQuantity"] == warehouse_qty

    def test_get_orders(self, adapter):
        response_data = {
            "GetOrder": {
                "Order": [
                    {
                        "OrderID": "N10001",
                        "OrderStatus": "New",
                        "GrandTotal": "59.99",
                    }
                ]
            }
        }
        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.get_orders(status="New")
        assert result == response_data
        body = mock_post.call_args.kwargs["json"]
        assert body["Filter"]["OrderStatus"] == "New"

    def test_update_order_with_tracking(self, adapter):
        response_data = {"UpdateOrder": {"Order": [{"OrderID": "N10001", "Result": "Success"}]}}
        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.update_order(
                order_id="N10001",
                status="Dispatched",
                tracking="TRK123456",
                carrier="Australia Post",
            )
        assert result == response_data
        body = mock_post.call_args.kwargs["json"]
        order = body["Order"][0]
        assert order["OrderID"] == "N10001"
        assert order["OrderStatus"] == "Dispatched"
        tracking_details = order["OrderLine"]["TrackingDetails"]
        assert tracking_details["TrackingNumber"] == "TRK123456"
        assert tracking_details["ShippingMethod"] == "Australia Post"

    def test_add_rma(self, adapter):
        response_data = {"AddRma": {"Rma": [{"RmaID": "R001", "Result": "Success"}]}}
        lines = [
            {
                "SKU": "SKU-001",
                "Quantity": "1",
                "ReturnReason": "Faulty",
                "ResolutionOutcome": "Refund",
                "RefundSubtotal": "29.99",
                "TaxCode": "GST",
                "WarehouseID": "1",
            }
        ]
        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.add_rma(
                order_id="N10001",
                invoice_number="INV-10001",
                customer_username="customer@example.com",
                lines=lines,
            )
        assert result == response_data
        body = mock_post.call_args.kwargs["json"]
        rma = body["Rma"][0]
        assert rma["OrderID"] == "N10001"
        assert rma["RmaStatus"] == "Open"
        assert rma["RmaLine"] == lines

    def test_rate_limit_retry(self, adapter):
        success_data = {"AddItem": {"Item": [{"SKU": "SKU-001", "Result": "Success"}]}}
        rate_limit_response = _mock_response({}, status_code=429)
        success_response = _mock_response(success_data, status_code=200)

        with patch("requests.post", side_effect=[rate_limit_response, success_response]) as mock_post:
            with patch("time.sleep"):
                result = adapter.add_item(sku="SKU-001", name="Test", price="9.99")

        assert mock_post.call_count == 2
        assert result == success_data
