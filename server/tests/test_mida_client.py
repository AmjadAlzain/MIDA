"""
Unit tests for MIDA API Client.

Tests use mocked HTTP responses (no real network calls).
"""

import json
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
import httpx

from app.clients.mida_client import (
    MidaClient,
    MidaCertificateNotFoundError,
    MidaApiError,
    MidaClientConfigError,
    TTLCache,
    get_certificate_by_number,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_settings():
    """Mock settings with MIDA API configuration."""
    settings = MagicMock()
    settings.mida_api_base_url = "http://mida-service:8000"
    settings.mida_api_timeout_seconds = 10
    settings.mida_api_cache_ttl_seconds = 60
    return settings


@pytest.fixture
def sample_certificate_response():
    """Sample API response for a certificate with items."""
    return {
        "items": [
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "certificate_number": "MIDA/001/2024",
                "company_name": "Test Company Sdn Bhd",
                "exemption_start_date": "2024-01-01",
                "exemption_end_date": "2024-12-31",
                "status": "confirmed",
                "source_filename": "cert.pdf",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "items": [
                    {
                        "id": "item-1",
                        "line_no": 1,
                        "hs_code": "84715000",
                        "item_name": "COMPUTER PROCESSING UNIT",
                        "uom": "UNIT",
                        "approved_quantity": "500.000",
                        "port_klang_qty": "200.000",
                        "klia_qty": "150.000",
                        "bukit_kayu_hitam_qty": "150.000",
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-01-15T10:00:00Z",
                    },
                    {
                        "id": "item-2",
                        "line_no": 2,
                        "hs_code": "85176290",
                        "item_name": "NETWORK ROUTER",
                        "uom": "UNIT",
                        "approved_quantity": "100.000",
                        "port_klang_qty": None,
                        "klia_qty": None,
                        "bukit_kayu_hitam_qty": None,
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-01-15T10:00:00Z",
                    },
                ],
            }
        ],
        "total": 1,
        "limit": 1,
        "offset": 0,
    }


@pytest.fixture
def empty_response():
    """Sample API response with no certificates found."""
    return {
        "items": [],
        "total": 0,
        "limit": 1,
        "offset": 0,
    }


# =============================================================================
# TTLCache Tests
# =============================================================================


class TestTTLCache:
    """Tests for the in-memory TTL cache."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = TTLCache(ttl_seconds=60)
        mock_data = MagicMock()
        
        cache.set("key1", mock_data)
        result = cache.get("key1")
        
        assert result is mock_data

    def test_get_missing_key(self):
        """Test getting a non-existent key returns None."""
        cache = TTLCache(ttl_seconds=60)
        
        result = cache.get("nonexistent")
        
        assert result is None

    def test_expiration(self):
        """Test that entries expire after TTL."""
        cache = TTLCache(ttl_seconds=1)  # 1 second TTL
        mock_data = MagicMock()
        
        cache.set("key1", mock_data)
        assert cache.get("key1") is mock_data
        
        # Wait for expiration
        time.sleep(1.1)
        
        assert cache.get("key1") is None

    def test_invalidate(self):
        """Test invalidating a specific key."""
        cache = TTLCache(ttl_seconds=60)
        mock_data = MagicMock()
        
        cache.set("key1", mock_data)
        cache.set("key2", mock_data)
        
        cache.invalidate("key1")
        
        assert cache.get("key1") is None
        assert cache.get("key2") is mock_data

    def test_clear(self):
        """Test clearing all entries."""
        cache = TTLCache(ttl_seconds=60)
        mock_data = MagicMock()
        
        cache.set("key1", mock_data)
        cache.set("key2", mock_data)
        
        cache.clear()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = TTLCache(ttl_seconds=1)
        mock_data = MagicMock()
        
        cache.set("key1", mock_data)
        cache.set("key2", mock_data)
        
        time.sleep(1.1)
        
        removed = cache.cleanup_expired()
        
        assert removed == 2


# =============================================================================
# MidaClient Tests
# =============================================================================


class TestMidaClient:
    """Tests for the MIDA API client."""

    def test_missing_base_url_raises_config_error(self, mock_settings):
        """Test that missing base URL raises configuration error."""
        mock_settings.mida_api_base_url = None
        
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            with pytest.raises(MidaClientConfigError) as exc_info:
                _ = client.base_url
            
            assert "MIDA_API_BASE_URL not configured" in str(exc_info.value)

    def test_successful_certificate_fetch(self, mock_settings, sample_certificate_response):
        """Test successfully fetching a certificate."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            # Mock the HTTP response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_certificate_response
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.return_value = mock_response
                client._http_client = mock_http
                
                result = client.get_certificate_by_number("MIDA/001/2024")
                
                # Verify header
                assert result.header.certificate_number == "MIDA/001/2024"
                assert result.header.company_name == "Test Company Sdn Bhd"
                assert result.header.status == "confirmed"
                
                # Verify items
                assert len(result.items) == 2
                assert result.items[0].hs_code == "84715000"
                assert result.items[0].item_name == "COMPUTER PROCESSING UNIT"
                assert result.items[0].approved_quantity == Decimal("500.000")
                assert result.items[1].hs_code == "85176290"

    def test_certificate_not_found_empty_list(self, mock_settings, empty_response):
        """Test that empty result raises not found error."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = empty_response
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.return_value = mock_response
                client._http_client = mock_http
                
                with pytest.raises(MidaCertificateNotFoundError) as exc_info:
                    client.get_certificate_by_number("UNKNOWN/999/2024")
                
                assert "UNKNOWN/999/2024" in str(exc_info.value)
                assert exc_info.value.status_code == 404

    def test_certificate_not_found_404_response(self, mock_settings):
        """Test that 404 response raises not found error."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 404
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.return_value = mock_response
                client._http_client = mock_http
                
                with pytest.raises(MidaCertificateNotFoundError):
                    client.get_certificate_by_number("NOTFOUND/001/2024")

    def test_api_error_response(self, mock_settings):
        """Test that non-2xx/non-404 raises API error."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"detail": "Internal server error"}
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.return_value = mock_response
                client._http_client = mock_http
                
                with pytest.raises(MidaApiError) as exc_info:
                    client.get_certificate_by_number("MIDA/001/2024")
                
                assert exc_info.value.status_code == 500

    def test_timeout_error(self, mock_settings):
        """Test that timeout raises API error with 504 status."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.side_effect = httpx.TimeoutException("Timeout")
                client._http_client = mock_http
                
                with pytest.raises(MidaApiError) as exc_info:
                    client.get_certificate_by_number("MIDA/001/2024")
                
                assert exc_info.value.status_code == 504
                assert "timed out" in str(exc_info.value).lower()

    def test_connection_error(self, mock_settings):
        """Test that connection error raises API error with 503 status."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.side_effect = httpx.ConnectError("Connection refused")
                client._http_client = mock_http
                
                with pytest.raises(MidaApiError) as exc_info:
                    client.get_certificate_by_number("MIDA/001/2024")
                
                assert exc_info.value.status_code == 503

    def test_caching_works(self, mock_settings, sample_certificate_response):
        """Test that responses are cached."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient(cache_ttl_seconds=60)
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_certificate_response
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.return_value = mock_response
                client._http_client = mock_http
                
                # First call - should hit API
                result1 = client.get_certificate_by_number("MIDA/001/2024")
                assert mock_http.get.call_count == 1
                
                # Second call - should use cache
                result2 = client.get_certificate_by_number("MIDA/001/2024")
                assert mock_http.get.call_count == 1  # No additional call
                
                # Results should be the same
                assert result1.header.certificate_number == result2.header.certificate_number

    def test_cache_bypass(self, mock_settings, sample_certificate_response):
        """Test that use_cache=False bypasses the cache."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient(cache_ttl_seconds=60)
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_certificate_response
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.return_value = mock_response
                client._http_client = mock_http
                
                # First call
                client.get_certificate_by_number("MIDA/001/2024", use_cache=True)
                assert mock_http.get.call_count == 1
                
                # Second call with cache bypass
                client.get_certificate_by_number("MIDA/001/2024", use_cache=False)
                assert mock_http.get.call_count == 2

    def test_empty_certificate_number_raises_not_found(self, mock_settings):
        """Test that empty certificate number raises not found."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient()
            
            with pytest.raises(MidaCertificateNotFoundError):
                client.get_certificate_by_number("")
            
            with pytest.raises(MidaCertificateNotFoundError):
                client.get_certificate_by_number("   ")

    def test_context_manager(self, mock_settings):
        """Test client as context manager."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            with MidaClient() as client:
                assert client._base_url == "http://mida-service:8000"
            
            # After exiting, client should be closed
            assert client._http_client is None

    def test_invalidate_cache(self, mock_settings, sample_certificate_response):
        """Test invalidating a specific cache entry."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            client = MidaClient(cache_ttl_seconds=60)
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_certificate_response
            
            with patch.object(client, "_http_client") as mock_http:
                mock_http.get.return_value = mock_response
                client._http_client = mock_http
                
                # Populate cache
                client.get_certificate_by_number("MIDA/001/2024")
                assert mock_http.get.call_count == 1
                
                # Invalidate
                client.invalidate_cache("MIDA/001/2024")
                
                # Next call should hit API again
                client.get_certificate_by_number("MIDA/001/2024")
                assert mock_http.get.call_count == 2


# =============================================================================
# Integration-style Tests (still mocked, but test full flow)
# =============================================================================


class TestGetCertificateByNumberFunction:
    """Tests for the module-level convenience function."""

    def test_function_uses_singleton_client(self, mock_settings, sample_certificate_response):
        """Test that the convenience function uses the shared client."""
        with patch("app.clients.mida_client.get_settings", return_value=mock_settings):
            with patch("app.clients.mida_client._client_instance", None):
                # Mock httpx.Client
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = sample_certificate_response
                
                mock_http_client = MagicMock()
                mock_http_client.get.return_value = mock_response
                
                with patch("httpx.Client", return_value=mock_http_client):
                    result = get_certificate_by_number("MIDA/001/2024")
                    
                    assert result.header.certificate_number == "MIDA/001/2024"
