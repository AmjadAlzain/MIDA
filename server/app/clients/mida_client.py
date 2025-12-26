"""
MIDA API Client.

Production-ready HTTP client for fetching certificate data from the MIDA backend.
Uses REST API calls instead of direct database access for portability and separation
of concerns (IT can deploy services separately).

Features:
- Fetches certificate header + items via REST API
- In-memory caching with configurable TTL to reduce API calls
- Clean error handling with structured responses
- Configurable timeout and base URL via environment variables

Environment Variables:
- MIDA_API_BASE_URL: Base URL of the MIDA API (e.g., http://mida-service:8000)
- MIDA_API_TIMEOUT_SECONDS: Request timeout in seconds (default: 10)
- MIDA_API_CACHE_TTL_SECONDS: Cache TTL in seconds (default: 60)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from threading import Lock
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MidaCertificateHeader:
    """Certificate header data from MIDA API."""

    id: str
    certificate_number: str
    company_name: str
    exemption_start_date: Optional[str] = None
    exemption_end_date: Optional[str] = None
    status: str = "draft"
    source_filename: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class MidaCertificateItem:
    """Certificate line item from MIDA API."""

    id: str
    line_no: int
    hs_code: str
    item_name: str
    uom: str
    approved_quantity: Optional[Decimal] = None
    port_klang_qty: Optional[Decimal] = None
    klia_qty: Optional[Decimal] = None
    bukit_kayu_hitam_qty: Optional[Decimal] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class MidaCertificateResponse:
    """Complete certificate response with header and items."""

    header: MidaCertificateHeader
    items: list[MidaCertificateItem] = field(default_factory=list)


# =============================================================================
# Exceptions
# =============================================================================


class MidaClientError(Exception):
    """Base exception for MIDA client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class MidaCertificateNotFoundError(MidaClientError):
    """Raised when a certificate is not found."""

    def __init__(self, certificate_number: str):
        super().__init__(
            f"MIDA certificate '{certificate_number}' not found",
            status_code=404,
        )
        self.certificate_number = certificate_number


class MidaApiError(MidaClientError):
    """Raised when MIDA API returns an error response."""

    pass


class MidaClientConfigError(MidaClientError):
    """Raised when MIDA client is not properly configured."""

    pass


# =============================================================================
# In-Memory Cache
# =============================================================================


@dataclass
class CacheEntry:
    """A cached response with timestamp."""

    data: MidaCertificateResponse
    timestamp: float


class TTLCache:
    """
    Thread-safe in-memory cache with TTL expiration.

    Simple but effective caching to avoid repeated API calls for the same certificate.
    """

    def __init__(self, ttl_seconds: int = 60):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[MidaCertificateResponse]:
        """Get a cached value if it exists and hasn't expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # Check if expired
            if time.time() - entry.timestamp > self._ttl:
                del self._cache[key]
                return None

            return entry.data

    def set(self, key: str, value: MidaCertificateResponse) -> None:
        """Store a value in the cache."""
        with self._lock:
            self._cache[key] = CacheEntry(data=value, timestamp=time.time())

    def invalidate(self, key: str) -> None:
        """Remove a specific key from the cache."""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        with self._lock:
            now = time.time()
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if now - entry.timestamp > self._ttl
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)


# =============================================================================
# MIDA Client
# =============================================================================


class MidaClient:
    """
    Production-ready HTTP client for MIDA API.

    Usage:
        client = MidaClient()
        try:
            cert = client.get_certificate_by_number("MIDA/123/2024")
            print(cert.header.company_name)
            for item in cert.items:
                print(f"{item.line_no}: {item.hs_code} - {item.item_name}")
        except MidaCertificateNotFoundError:
            print("Certificate not found")
        except MidaApiError as e:
            print(f"API error: {e.message}")
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        cache_ttl_seconds: Optional[int] = None,
    ):
        """
        Initialize the MIDA client.

        Args:
            base_url: MIDA API base URL (falls back to MIDA_API_BASE_URL env var)
            timeout_seconds: Request timeout (falls back to MIDA_API_TIMEOUT_SECONDS)
            cache_ttl_seconds: Cache TTL (falls back to MIDA_API_CACHE_TTL_SECONDS)
        """
        settings = get_settings()

        self._base_url = base_url or settings.mida_api_base_url
        self._timeout = timeout_seconds or settings.mida_api_timeout_seconds
        cache_ttl = cache_ttl_seconds or settings.mida_api_cache_ttl_seconds

        self._cache = TTLCache(ttl_seconds=cache_ttl)
        self._http_client: Optional[httpx.Client] = None

    @property
    def base_url(self) -> str:
        """Get the configured base URL, raising if not set."""
        if not self._base_url:
            raise MidaClientConfigError(
                "MIDA_API_BASE_URL not configured. "
                "Set the environment variable or pass base_url to MidaClient."
            )
        return self._base_url.rstrip("/")

    @property
    def http_client(self) -> httpx.Client:
        """Get or create the HTTP client (lazy initialization)."""
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "MIDA-Converter-Client/1.0",
                },
            )
        return self._http_client

    def close(self) -> None:
        """Close the HTTP client and clear cache."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None
        self._cache.clear()

    def __enter__(self) -> "MidaClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def get_certificate_by_number(
        self,
        certificate_number: str,
        use_cache: bool = True,
    ) -> MidaCertificateResponse:
        """
        Fetch a certificate by its number from the MIDA API.

        Calls GET /api/mida/certificates?certificate_number=...&status=confirmed&limit=1
        and returns the certificate header with items.

        Args:
            certificate_number: The MIDA certificate number to look up
            use_cache: Whether to use cached response (default: True)

        Returns:
            MidaCertificateResponse with header and items

        Raises:
            MidaCertificateNotFoundError: If certificate not found (404 or empty list)
            MidaApiError: If API returns non-2xx response
            MidaClientConfigError: If client is not properly configured
        """
        if not certificate_number or not certificate_number.strip():
            raise MidaCertificateNotFoundError(certificate_number or "<empty>")

        cert_num = certificate_number.strip()
        cache_key = f"cert:{cert_num}"

        # Check cache first
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for certificate: %s", cert_num)
                return cached

        logger.debug("Fetching certificate from API: %s", cert_num)

        try:
            response = self.http_client.get(
                "/api/mida/certificates",
                params={
                    "certificate_number": cert_num,
                    "status": "confirmed",
                    "limit": 1,
                },
            )
        except httpx.TimeoutException as exc:
            raise MidaApiError(
                f"Request timed out after {self._timeout}s",
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            # Sanitize error message to avoid leaking internal details
            raise MidaApiError(
                f"Failed to connect to MIDA API: {type(exc).__name__}",
                status_code=503,
            ) from exc

        # Handle non-2xx responses
        if response.status_code == 404:
            raise MidaCertificateNotFoundError(cert_num)

        if response.status_code >= 400:
            # Sanitize error message
            detail = self._extract_error_detail(response)
            raise MidaApiError(
                f"MIDA API error: {detail}",
                status_code=response.status_code,
            )

        # Parse response
        try:
            data = response.json()
        except Exception as exc:
            raise MidaApiError(
                "Invalid JSON response from MIDA API",
                status_code=500,
            ) from exc

        # The list endpoint returns {"items": [...], "total": N, ...}
        items_list = data.get("items", [])

        if not items_list:
            raise MidaCertificateNotFoundError(cert_num)

        # Take the first (and should be only) certificate
        cert_data = items_list[0]
        result = self._parse_certificate_response(cert_data)

        # Cache the result
        if use_cache:
            self._cache.set(cache_key, result)
            logger.debug("Cached certificate: %s", cert_num)

        return result

    def _parse_certificate_response(
        self, data: dict[str, Any]
    ) -> MidaCertificateResponse:
        """Parse API response into MidaCertificateResponse."""
        header = MidaCertificateHeader(
            id=str(data.get("id", "")),
            certificate_number=data.get("certificate_number", ""),
            company_name=data.get("company_name", ""),
            exemption_start_date=data.get("exemption_start_date"),
            exemption_end_date=data.get("exemption_end_date"),
            status=data.get("status", "draft"),
            source_filename=data.get("source_filename"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

        items: list[MidaCertificateItem] = []
        for item_data in data.get("items", []):
            items.append(
                MidaCertificateItem(
                    id=str(item_data.get("id", "")),
                    line_no=item_data.get("line_no", 0),
                    hs_code=item_data.get("hs_code", ""),
                    item_name=item_data.get("item_name", ""),
                    uom=item_data.get("uom", ""),
                    approved_quantity=self._parse_decimal(
                        item_data.get("approved_quantity")
                    ),
                    port_klang_qty=self._parse_decimal(item_data.get("port_klang_qty")),
                    klia_qty=self._parse_decimal(item_data.get("klia_qty")),
                    bukit_kayu_hitam_qty=self._parse_decimal(
                        item_data.get("bukit_kayu_hitam_qty")
                    ),
                    created_at=item_data.get("created_at"),
                    updated_at=item_data.get("updated_at"),
                )
            )

        return MidaCertificateResponse(header=header, items=items)

    @staticmethod
    def _parse_decimal(value: Any) -> Optional[Decimal]:
        """Safely parse a value to Decimal."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Extract error detail from response, sanitizing sensitive info."""
        try:
            data = response.json()
            if isinstance(data, dict):
                detail = data.get("detail")
                if isinstance(detail, str):
                    return detail
                if isinstance(detail, dict):
                    return detail.get("detail", str(detail))
            return f"HTTP {response.status_code}"
        except Exception:
            return f"HTTP {response.status_code}"

    def invalidate_cache(self, certificate_number: str) -> None:
        """Invalidate cached data for a specific certificate."""
        cache_key = f"cert:{certificate_number.strip()}"
        self._cache.invalidate(cache_key)

    def clear_cache(self) -> None:
        """Clear all cached certificates."""
        self._cache.clear()


# =============================================================================
# Module-level client instance (singleton pattern)
# =============================================================================

_client_instance: Optional[MidaClient] = None
_client_lock = Lock()


def get_mida_client() -> MidaClient:
    """
    Get the shared MIDA client instance (singleton).

    This provides a single, reusable client with connection pooling and caching.
    For testing, use MidaClient directly with custom parameters.
    """
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                _client_instance = MidaClient()
    return _client_instance


def get_certificate_by_number(
    certificate_number: str,
    use_cache: bool = True,
) -> MidaCertificateResponse:
    """
    Convenience function to fetch a certificate using the shared client.

    Args:
        certificate_number: The MIDA certificate number
        use_cache: Whether to use cached response (default: True)

    Returns:
        MidaCertificateResponse with header and items

    Raises:
        MidaCertificateNotFoundError: If certificate not found
        MidaApiError: If API returns an error
        MidaClientConfigError: If client is not configured
    """
    return get_mida_client().get_certificate_by_number(
        certificate_number, use_cache=use_cache
    )
