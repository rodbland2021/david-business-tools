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
