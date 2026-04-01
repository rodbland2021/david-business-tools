import json
from unittest.mock import MagicMock, patch

import pytest

from adapters.kogan import KoganAdapter


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
    return KoganAdapter(
        seller_id="test-seller",
        seller_token="test-token-123",
        environment="uat",
    )


class TestKoganAdapter:
    def test_create_product(self, adapter):
        pending_data = {
            "status": "AsyncResponsePending",
            "pending_url": "https://nimda-marketplace.aws.kgn.io/api/marketplace/v2/tasks/abc123/",
        }
        complete_data = {
            "status": "Complete",
            "sku": "TEST-SKU-001",
            "result": "success",
        }

        with patch("requests.post", return_value=_mock_response(pending_data)) as mock_post, \
             patch("requests.get", return_value=_mock_response(complete_data)) as mock_get, \
             patch("time.sleep"):
            result = adapter.create_product(
                sku="TEST-SKU-001",
                title="Test Product",
                description="A test product description",
                brand="TestBrand",
                category="electronics",
                price=29.99,
                images=["https://example.com/image1.jpg"],
                shipping=5.00,
                handling_days=2,
            )

        assert result["status"] == "Complete"
        assert result["sku"] == "TEST-SKU-001"
        mock_post.assert_called_once()
        mock_get.assert_called_once()

    def test_update_stock_price(self, adapter):
        pending_data = {
            "status": "AsyncResponsePending",
            "pending_url": "https://nimda-marketplace.aws.kgn.io/api/marketplace/v2/tasks/def456/",
        }
        complete_data = {
            "status": "Complete",
            "sku": "TEST-SKU-001",
            "stock": 50,
            "price": 25.99,
        }

        with patch("requests.post", return_value=_mock_response(pending_data)) as mock_post, \
             patch("requests.get", return_value=_mock_response(complete_data)) as mock_get, \
             patch("time.sleep"):
            result = adapter.update_stock_price(
                sku="TEST-SKU-001",
                stock=50,
                price=25.99,
            )

        assert result["status"] == "Complete"
        assert result["stock"] == 50
        mock_post.assert_called_once()
        mock_get.assert_called_once()
        post_body = mock_post.call_args.kwargs["json"]
        assert post_body["sku"] == "TEST-SKU-001"
        assert post_body["offer_data"]["stock"] == 50
        assert post_body["offer_data"]["price"] == 25.99

    def test_get_orders(self, adapter):
        response_data = {
            "results": [
                {
                    "order_ref": "KOG-10001",
                    "status": "ReleasedForShipment",
                    "items": [{"sku": "TEST-SKU-001", "quantity": 1}],
                }
            ],
            "count": 1,
        }

        with patch("requests.get", return_value=_mock_response(response_data)) as mock_get:
            result = adapter.get_orders(status="ReleasedForShipment")

        assert result["count"] == 1
        assert result["results"][0]["order_ref"] == "KOG-10001"
        mock_get.assert_called_once()
        call_params = mock_get.call_args.kwargs["params"]
        assert call_params["status"] == "ReleasedForShipment"

    def test_fulfill_order(self, adapter):
        response_data = {
            "order_ref": "KOG-10001",
            "status": "Dispatched",
        }
        items = [
            {
                "order_item_id": "item-001",
                "sku": "TEST-SKU-001",
                "quantity": 1,
                "tracking": "TRK123456",
                "carrier": "Australia Post",
            }
        ]

        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.fulfill_order(order_ref="KOG-10001", items=items)

        assert result["status"] == "Dispatched"
        mock_post.assert_called_once()
        post_body = mock_post.call_args.kwargs["json"]
        assert post_body["order_ref"] == "KOG-10001"
        assert post_body["items"][0]["sku"] == "TEST-SKU-001"
        assert post_body["items"][0]["tracking"] == "TRK123456"
        assert "shipped_date" in post_body["items"][0]

    def test_cancel_order(self, adapter):
        response_data = {
            "order_ref": "KOG-10001",
            "status": "Cancelled",
        }
        items = [
            {
                "id": "item-001",
                "sku": "TEST-SKU-001",
                "quantity": 1,
                "reason": "ItemNotAvailable",
            }
        ]

        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.cancel_order(order_ref="KOG-10001", items=items)

        assert result["status"] == "Cancelled"
        mock_post.assert_called_once()
        post_url = mock_post.call_args.args[0]
        assert "KOG-10001" in post_url
        assert "cancel" in post_url
        post_body = mock_post.call_args.kwargs["json"]
        assert post_body["items"][0]["reason"] == "ItemNotAvailable"

    def test_refund_order(self, adapter):
        response_data = {
            "order_ref": "KOG-10001",
            "status": "Refunded",
            "refund_amount": 29.99,
        }
        items = [
            {
                "id": "item-001",
                "sku": "TEST-SKU-001",
                "quantity": 1,
                "reason": "Faulty Item",
            }
        ]

        with patch("requests.post", return_value=_mock_response(response_data)) as mock_post:
            result = adapter.refund_order(order_ref="KOG-10001", items=items)

        assert result["status"] == "Refunded"
        mock_post.assert_called_once()
        post_url = mock_post.call_args.args[0]
        assert "KOG-10001" in post_url
        assert "refund" in post_url
        post_body = mock_post.call_args.kwargs["json"]
        assert post_body["items"][0]["reason"] == "Faulty Item"

    def test_get_categories(self, adapter):
        response_data = {
            "results": [
                {"id": "electronics", "name": "Electronics"},
                {"id": "home-garden", "name": "Home & Garden"},
            ]
        }

        with patch("requests.get", return_value=_mock_response(response_data)) as mock_get:
            result = adapter.get_categories()

        assert len(result["results"]) == 2
        assert result["results"][0]["id"] == "electronics"
        mock_get.assert_called_once()

    def test_rate_limit_retry(self, adapter):
        success_data = {
            "results": [{"order_ref": "KOG-10001", "status": "ReleasedForShipment"}],
            "count": 1,
        }
        rate_limit_response = _mock_response({}, status_code=429)
        success_response = _mock_response(success_data, status_code=200)

        with patch("requests.get", side_effect=[rate_limit_response, success_response]) as mock_get, \
             patch("time.sleep"):
            result = adapter.get_orders()

        assert mock_get.call_count == 2
        assert result["count"] == 1
