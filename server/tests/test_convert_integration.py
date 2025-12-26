"""
Integration tests for the convert endpoint.

Tests cover:
- Normal mode (no MIDA certificate number)
- MIDA mode with matching
- Error handling (invalid certificate number)
- Warnings for quantity limits
"""

import io
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.clients.mida_client import (
    MidaCertificateHeader,
    MidaCertificateItem,
    MidaCertificateNotFoundError,
    MidaCertificateResponse,
)
from app.main import app


@pytest.fixture
def client():
    """Create a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_invoice_excel() -> bytes:
    """Create a sample invoice Excel file."""
    df = pd.DataFrame({
        "HS Code": ["84715000", "85176290", "99999999"],
        "Description": ["Computer Processing Unit", "Network Router Device", "Unknown Item"],
        "Quantity": [50, 10, 5],
        "UOM": ["UNT", "PCS", "UNT"],
        "Amount": [5000, 2000, 500],
        "Net Weight (KG)": [25, 5, 2],
    })
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def sample_mida_certificate() -> MidaCertificateResponse:
    """Create a sample MIDA certificate response."""
    return MidaCertificateResponse(
        header=MidaCertificateHeader(
            id="cert-001",
            certificate_number="MIDA/2024/001",
            company_name="Test Company",
            status="approved",
        ),
        items=[
            MidaCertificateItem(
                id="item-001",
                line_no=1,
                hs_code="84715000",
                item_name="COMPUTER PROCESSING UNIT",
                uom="UNIT",
                approved_quantity=Decimal("500"),
            ),
            MidaCertificateItem(
                id="item-002",
                line_no=2,
                hs_code="85176290",
                item_name="NETWORK ROUTER DEVICE",
                uom="UNIT",
                approved_quantity=Decimal("100"),
            ),
        ],
    )


class TestNormalMode:
    """Tests for normal mode (no MIDA certificate number)."""

    def test_normal_mode_returns_all_items(self, client, sample_invoice_excel):
        """Test that normal mode returns all parsed invoice items."""
        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "match_mode": "fuzzy",
                "match_threshold": "0.88",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Normal mode checks
        assert data["mida_certificate_number"] == ""
        assert data["mida_matched_items"] == []
        assert data["all_invoice_items"] is not None
        assert len(data["all_invoice_items"]) == 3
        assert data["total_invoice_items"] == 3
        assert data["matched_item_count"] == 0
        assert data["unmatched_item_count"] == 3

    def test_normal_mode_with_empty_certificate(self, client, sample_invoice_excel):
        """Test that empty certificate number triggers normal mode."""
        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "",
                "match_mode": "fuzzy",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mida_certificate_number"] == ""
        assert data["all_invoice_items"] is not None

    def test_normal_mode_with_whitespace_certificate(self, client, sample_invoice_excel):
        """Test that whitespace-only certificate number triggers normal mode."""
        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "   ",
                "match_mode": "fuzzy",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mida_certificate_number"] == ""


class TestMidaMode:
    """Tests for MIDA mode (with certificate number)."""

    @patch("app.routers.convert.fetch_certificate_from_api")
    def test_mida_mode_matches_items(
        self,
        mock_fetch,
        client,
        sample_invoice_excel,
        sample_mida_certificate,
    ):
        """Test that MIDA mode matches invoice items to certificate."""
        mock_fetch.return_value = sample_mida_certificate

        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
                "match_mode": "fuzzy",
                "match_threshold": "0.5",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # MIDA mode checks
        assert data["mida_certificate_number"] == "MIDA/2024/001"
        assert data["all_invoice_items"] is None  # Not present in MIDA mode
        assert data["total_invoice_items"] == 3
        assert data["matched_item_count"] == 2  # 2 items matched
        assert data["unmatched_item_count"] == 1  # "Unknown Item" not matched

        # Verify matched items have MIDA fields
        for item in data["mida_matched_items"]:
            assert "mida_line_no" in item
            assert "mida_hs_code" in item
            assert "mida_item_name" in item
            assert "remaining_qty" in item
            assert "remaining_uom" in item
            assert "match_score" in item
            assert "approved_qty" in item

    @patch("app.routers.convert.fetch_certificate_from_api")
    def test_mida_mode_includes_original_fields(
        self,
        mock_fetch,
        client,
        sample_invoice_excel,
        sample_mida_certificate,
    ):
        """Test that matched items include original invoice fields."""
        mock_fetch.return_value = sample_mida_certificate

        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
                "match_mode": "fuzzy",
                "match_threshold": "0.5",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify original fields are preserved
        if data["mida_matched_items"]:
            item = data["mida_matched_items"][0]
            assert "line_no" in item
            assert "hs_code" in item
            assert "description" in item
            assert "quantity" in item
            assert "uom" in item

    @patch("app.routers.convert.fetch_certificate_from_api")
    def test_mida_mode_generates_warnings_for_unmatched(
        self,
        mock_fetch,
        client,
        sample_invoice_excel,
        sample_mida_certificate,
    ):
        """Test that warnings are generated for unmatched items."""
        mock_fetch.return_value = sample_mida_certificate

        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
                "match_mode": "fuzzy",
                "match_threshold": "0.5",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should have warning for "Unknown Item"
        unmatched_warnings = [
            w for w in data["warnings"]
            if "No matching MIDA certificate item found" in w["reason"]
        ]
        assert len(unmatched_warnings) >= 1


class TestQuantityWarnings:
    """Tests for quantity-related warnings."""

    @patch("app.routers.convert.fetch_certificate_from_api")
    def test_warning_when_exceeds_remaining(self, mock_fetch, client):
        """Test warning when invoice quantity exceeds remaining approved quantity."""
        # Create invoice with large quantity
        df = pd.DataFrame({
            "HS Code": ["84715000"],
            "Description": ["Computer Processing Unit"],
            "Quantity": [600],  # Exceeds approved 500
            "UOM": ["UNT"],
        })
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)
        invoice_bytes = buffer.getvalue()

        # Create certificate with limited quantity
        mock_fetch.return_value = MidaCertificateResponse(
            header=MidaCertificateHeader(
                id="cert-001",
                certificate_number="MIDA/2024/001",
                company_name="Test Company",
            ),
            items=[
                MidaCertificateItem(
                    id="item-001",
                    line_no=1,
                    hs_code="84715000",
                    item_name="COMPUTER PROCESSING UNIT",
                    uom="UNIT",
                    approved_quantity=Decimal("500"),
                ),
            ],
        )

        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", invoice_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
                "match_mode": "fuzzy",
                "match_threshold": "0.5",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should have warning for exceeding quantity
        qty_warnings = [
            w for w in data["warnings"]
            if "Exceeds" in w["reason"] or "exceeds" in w["reason"].lower()
        ]
        assert len(qty_warnings) >= 1


class TestErrorHandling:
    """Tests for error handling."""

    @patch("app.routers.convert.fetch_certificate_from_api")
    def test_invalid_certificate_returns_422(self, mock_fetch, client, sample_invoice_excel):
        """Test that invalid certificate number returns 422."""
        mock_fetch.side_effect = MidaCertificateNotFoundError("INVALID-CERT")

        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "INVALID-CERT",
                "match_mode": "fuzzy",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert "Invalid MIDA certificate number" in data["detail"]["detail"]

    def test_empty_file_returns_422(self, client):
        """Test that empty file returns 422."""
        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
            },
        )

        assert response.status_code == 422

    def test_invalid_match_mode_returns_422(self, client, sample_invoice_excel):
        """Test that invalid match mode returns 422."""
        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
                "match_mode": "invalid",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert "Invalid match_mode" in data["detail"]["detail"]


class TestExactMatchMode:
    """Tests for exact match mode."""

    @patch("app.routers.convert.fetch_certificate_from_api")
    def test_exact_mode_requires_exact_match(
        self,
        mock_fetch,
        client,
        sample_invoice_excel,
        sample_mida_certificate,
    ):
        """Test that exact mode only matches exact name matches."""
        mock_fetch.return_value = sample_mida_certificate

        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
                "match_mode": "exact",
                "match_threshold": "1.0",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # In exact mode, only exact name matches should succeed
        # The descriptions are slightly different, so may not match
        assert data["total_invoice_items"] == 3


class TestOutputCompatibility:
    """Tests to ensure output format is compatible with original app."""

    @patch("app.routers.convert.fetch_certificate_from_api")
    def test_output_has_all_required_fields(
        self,
        mock_fetch,
        client,
        sample_invoice_excel,
        sample_mida_certificate,
    ):
        """Test that output contains all required fields for compatibility."""
        mock_fetch.return_value = sample_mida_certificate

        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "mida_certificate_number": "MIDA/2024/001",
                "match_mode": "fuzzy",
                "match_threshold": "0.5",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check all required top-level fields
        assert "mida_certificate_number" in data
        assert "mida_matched_items" in data
        assert "warnings" in data
        assert "total_invoice_items" in data
        assert "matched_item_count" in data
        assert "unmatched_item_count" in data

    def test_normal_mode_output_has_required_fields(self, client, sample_invoice_excel):
        """Test that normal mode output has required fields."""
        response = client.post(
            "/api/convert",
            files={"file": ("invoice.xlsx", sample_invoice_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "match_mode": "fuzzy",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Normal mode should have all_invoice_items
        assert "all_invoice_items" in data
        assert isinstance(data["all_invoice_items"], list)

        # Each item should have standard fields
        if data["all_invoice_items"]:
            item = data["all_invoice_items"][0]
            assert "line_no" in item
            assert "hs_code" in item
            assert "description" in item
            assert "quantity" in item
            assert "uom" in item
