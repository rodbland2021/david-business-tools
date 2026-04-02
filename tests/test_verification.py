import base64
import json
from unittest.mock import MagicMock, patch


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
            "Item": [{"SKU": "ML-T480", "Name": "Lenovo ThinkPad T480", "Description": "14-inch laptop", "Brand": "Lenovo", "Model": "T480", "DefaultPrice": "549.00", "Images": {"Image": ["https://cdn.example.com/img1.jpg"]}}]
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
        mock_neto.get_item.return_value = {"Item": [{"SKU": "ML-BARE", "Name": "No Image Product", "Description": "", "Brand": "", "Model": "", "DefaultPrice": "10.00", "Images": {}}]}
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
        mock_neto.get_item.return_value = {"Item": [{"SKU": "ML-MANY", "Name": "Many Images", "Description": "", "Brand": "", "Model": "", "DefaultPrice": "99.00", "Images": {"Image": ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg", "https://cdn.example.com/3.jpg"]}}]}
        mock_get_neto.return_value = mock_neto
        mock_get.return_value = _mock_image_response()
        result = json.loads(_neto_verify_listing("ML-MANY", max_images=1))
        assert result["image_count"] == 1
        assert len(result["images"]) == 1


class TestNetoVerifyListings:
    @patch("tools.verification_tools._get_neto")
    @patch("requests.get")
    def test_returns_batch_with_summary(self, mock_get, mock_get_neto):
        from tools.verification_tools import _neto_verify_listings
        mock_neto = MagicMock()
        mock_neto.get_items.return_value = {
            "Item": [
                {"SKU": "SKU-001", "Name": "Product One", "Description": "Desc one", "Brand": "Brand1", "Model": "M1", "DefaultPrice": "100.00", "Images": {"Image": ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg"]}},
                {"SKU": "SKU-002", "Name": "Product Two", "Description": "Desc two", "Brand": "Brand2", "Model": "M2", "DefaultPrice": "200.00", "Images": {}},
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
            "Item": [{"SKU": "SKU-001", "Name": "Product", "Description": "", "Brand": "", "Model": "", "DefaultPrice": "50.00", "Images": {"Image": ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg", "https://cdn.example.com/3.jpg"]}}]
        }
        mock_get_neto.return_value = mock_neto
        mock_get.return_value = _mock_image_response()
        result = json.loads(_neto_verify_listings(max_images=1))
        assert result["products"][0]["image_count"] == 1
        assert result["total_images"] == 1
