"""
MIDA Certificate Workflow Tests.

These tests cover the critical path for certificate CRUD operations:
- Create draft
- Update draft (replace items)
- Confirm certificate
- Attempt update on confirmed (expect 409)
- Cascade replace-items verification

Note: These tests require PostgreSQL for full compatibility (JSONB, UUID).
For CI, use a dockerized PostgreSQL instance.
SQLite will NOT work due to JSONB/UUID column types.

To run locally with test database:
    DATABASE_URL=postgresql://user:pass@localhost:5432/mida_test pytest server/tests/

To skip integration tests if no database:
    pytest server/tests/ -m "not integration"
"""

import pytest
from decimal import Decimal
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_db
from app.db.base import Base
from app.config import get_settings


# Test fixtures and database setup
settings = get_settings()

# Check if we have a test database configured
HAS_TEST_DB = settings.database_url is not None

# Marker for integration tests that require database
integration = pytest.mark.skipif(
    not HAS_TEST_DB,
    reason="No DATABASE_URL configured - skipping integration tests"
)


@pytest.fixture(scope="module")
def test_engine():
    """Create test database engine."""
    if not HAS_TEST_DB:
        pytest.skip("No DATABASE_URL configured")
    
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Don't drop tables - let migrations handle schema


@pytest.fixture(scope="function")
def test_db(test_engine):
    """Create a new database session for each test."""
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    db = TestingSessionLocal()
    
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture(scope="function")
def client(test_db):
    """Create test client with database dependency override."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


# Sample test data
def make_draft_payload(cert_num: str = None, num_items: int = 2):
    """Generate a test draft certificate payload."""
    if cert_num is None:
        cert_num = f"TEST-{uuid4().hex[:8].upper()}"
    
    return {
        "header": {
            "certificate_number": cert_num,
            "company_name": "Test Company Sdn Bhd",
            "exemption_start_date": "2024-01-01",
            "exemption_end_date": "2024-12-31",
            "source_filename": "test.pdf"
        },
        "items": [
            {
                "line_no": i + 1,
                "hs_code": f"8471.30.{i:02d}",
                "item_name": f"Test Item {i + 1}",
                "approved_quantity": str(100 * (i + 1)),
                "uom": "UNIT",
                "port_klang_qty": str(50 * (i + 1)),
                "klia_qty": str(30 * (i + 1)),
                "bukit_kayu_hitam_qty": str(20 * (i + 1))
            }
            for i in range(num_items)
        ],
        "raw_ocr_json": {"test": True, "pages": 1}
    }


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@integration
class TestCertificateWorkflow:
    """End-to-end workflow tests for certificate CRUD."""

    def test_create_draft_success(self, client):
        """Test creating a new draft certificate."""
        payload = make_draft_payload()
        
        response = client.post("/api/mida/certificates/draft", json=payload)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["certificate_number"] == payload["header"]["certificate_number"]
        assert data["company_name"] == payload["header"]["company_name"]
        assert data["status"] == "draft"
        assert len(data["items"]) == 2
        assert "id" in data

    def test_update_draft_replaces_items(self, client):
        """Test that updating a draft replaces all items."""
        # Create draft with 2 items
        payload = make_draft_payload(num_items=2)
        create_response = client.post("/api/mida/certificates/draft", json=payload)
        assert create_response.status_code == status.HTTP_201_CREATED
        cert_id = create_response.json()["id"]
        
        # Update with 3 items
        update_payload = {
            "header": payload["header"],
            "items": [
                {
                    "line_no": i + 1,
                    "hs_code": f"9999.99.{i:02d}",
                    "item_name": f"Updated Item {i + 1}",
                    "approved_quantity": str(999),
                    "uom": "PCS"
                }
                for i in range(3)
            ]
        }
        
        update_response = client.put(f"/api/mida/certificates/{cert_id}", json=update_payload)
        
        assert update_response.status_code == status.HTTP_200_OK
        data = update_response.json()
        assert len(data["items"]) == 3  # Items replaced, not appended
        assert all("9999.99" in item["hs_code"] for item in data["items"])

    def test_confirm_certificate(self, client):
        """Test confirming a draft certificate."""
        payload = make_draft_payload()
        create_response = client.post("/api/mida/certificates/draft", json=payload)
        cert_id = create_response.json()["id"]
        
        confirm_response = client.post(f"/api/mida/certificates/{cert_id}/confirm")
        
        assert confirm_response.status_code == status.HTTP_200_OK
        data = confirm_response.json()
        assert data["status"] == "confirmed"

    def test_confirm_is_idempotent(self, client):
        """Test that confirming an already-confirmed certificate succeeds."""
        payload = make_draft_payload()
        create_response = client.post("/api/mida/certificates/draft", json=payload)
        cert_id = create_response.json()["id"]
        
        # Confirm twice
        client.post(f"/api/mida/certificates/{cert_id}/confirm")
        second_confirm = client.post(f"/api/mida/certificates/{cert_id}/confirm")
        
        assert second_confirm.status_code == status.HTTP_200_OK
        assert second_confirm.json()["status"] == "confirmed"

    def test_update_confirmed_returns_409(self, client):
        """Test that updating a confirmed certificate returns 409."""
        payload = make_draft_payload()
        create_response = client.post("/api/mida/certificates/draft", json=payload)
        cert_id = create_response.json()["id"]
        
        # Confirm the certificate
        client.post(f"/api/mida/certificates/{cert_id}/confirm")
        
        # Attempt to update
        update_payload = {
            "header": payload["header"],
            "items": payload["items"]
        }
        update_response = client.put(f"/api/mida/certificates/{cert_id}", json=update_payload)
        
        assert update_response.status_code == status.HTTP_409_CONFLICT
        assert "confirmed" in update_response.json()["detail"].lower()

    def test_create_draft_on_confirmed_returns_409(self, client):
        """Test that creating a draft with same cert number as confirmed returns 409."""
        payload = make_draft_payload()
        
        # Create and confirm
        create_response = client.post("/api/mida/certificates/draft", json=payload)
        cert_id = create_response.json()["id"]
        client.post(f"/api/mida/certificates/{cert_id}/confirm")
        
        # Try to create again with same certificate_number
        second_create = client.post("/api/mida/certificates/draft", json=payload)
        
        assert second_create.status_code == status.HTTP_409_CONFLICT

    def test_get_certificate_by_id(self, client):
        """Test fetching a certificate by ID."""
        payload = make_draft_payload()
        create_response = client.post("/api/mida/certificates/draft", json=payload)
        cert_id = create_response.json()["id"]
        
        get_response = client.get(f"/api/mida/certificates/{cert_id}")
        
        assert get_response.status_code == status.HTTP_200_OK
        data = get_response.json()
        assert data["id"] == cert_id
        assert len(data["items"]) == 2

    def test_get_certificate_not_found(self, client):
        """Test fetching a non-existent certificate returns 404."""
        fake_id = str(uuid4())
        
        response = client.get(f"/api/mida/certificates/{fake_id}")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_certificates(self, client):
        """Test listing certificates with pagination."""
        # Create a few certificates
        for _ in range(3):
            client.post("/api/mida/certificates/draft", json=make_draft_payload())
        
        response = client.get("/api/mida/certificates?limit=10&offset=0")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert len(data["items"]) >= 3

    def test_list_certificates_filter_by_status(self, client):
        """Test filtering certificates by status."""
        # Create and confirm one
        payload = make_draft_payload()
        create_response = client.post("/api/mida/certificates/draft", json=payload)
        cert_id = create_response.json()["id"]
        client.post(f"/api/mida/certificates/{cert_id}/confirm")
        
        # Create a draft
        client.post("/api/mida/certificates/draft", json=make_draft_payload())
        
        # Filter by confirmed
        response = client.get("/api/mida/certificates?status=confirmed")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all(item["status"] == "confirmed" for item in data["items"])


# ============================================================================
# UNIT TESTS (no database required)
# ============================================================================

class TestSchemaValidation:
    """Test Pydantic schema validation."""

    def test_empty_certificate_number_rejected(self):
        """Test that empty certificate_number is rejected."""
        from pydantic import ValidationError
        from app.schemas.mida_certificate import CertificateHeaderIn
        
        with pytest.raises(ValidationError):
            CertificateHeaderIn(
                certificate_number="",
                company_name="Test Co"
            )

    def test_negative_line_no_rejected(self):
        """Test that negative line_no is rejected."""
        from pydantic import ValidationError
        from app.schemas.mida_certificate import CertificateItemIn
        
        with pytest.raises(ValidationError):
            CertificateItemIn(
                line_no=-1,
                hs_code="1234.56.78",
                item_name="Test",
                uom="UNIT"
            )

    def test_negative_quantity_rejected(self):
        """Test that negative quantity is rejected."""
        from pydantic import ValidationError
        from app.schemas.mida_certificate import CertificateItemIn
        
        with pytest.raises(ValidationError):
            CertificateItemIn(
                line_no=1,
                hs_code="1234.56.78",
                item_name="Test",
                uom="UNIT",
                approved_quantity=Decimal("-10")
            )

    def test_empty_items_rejected(self):
        """Test that empty items list is rejected."""
        from pydantic import ValidationError
        from app.schemas.mida_certificate import CertificateDraftCreateRequest, CertificateHeaderIn
        
        with pytest.raises(ValidationError):
            CertificateDraftCreateRequest(
                header=CertificateHeaderIn(
                    certificate_number="TEST-001",
                    company_name="Test Co"
                ),
                items=[]
            )

    def test_duplicate_line_no_rejected(self):
        """Test that duplicate line_no values are rejected."""
        from pydantic import ValidationError
        from app.schemas.mida_certificate import (
            CertificateDraftCreateRequest,
            CertificateHeaderIn,
            CertificateItemIn,
        )
        
        with pytest.raises(ValidationError) as exc_info:
            CertificateDraftCreateRequest(
                header=CertificateHeaderIn(
                    certificate_number="TEST-001",
                    company_name="Test Co"
                ),
                items=[
                    CertificateItemIn(line_no=1, hs_code="1234", item_name="A", uom="U"),
                    CertificateItemIn(line_no=1, hs_code="5678", item_name="B", uom="U"),
                ]
            )
        
        assert "Duplicate line_no" in str(exc_info.value)

    def test_valid_payload_accepted(self):
        """Test that valid payload is accepted."""
        from app.schemas.mida_certificate import (
            CertificateDraftCreateRequest,
            CertificateHeaderIn,
            CertificateItemIn,
        )
        
        payload = CertificateDraftCreateRequest(
            header=CertificateHeaderIn(
                certificate_number="TEST-001",
                company_name="Test Company"
            ),
            items=[
                CertificateItemIn(
                    line_no=1,
                    hs_code="8471.30.90",
                    item_name="Computer parts",
                    approved_quantity=Decimal("100.5"),
                    uom="UNIT"
                )
            ],
            raw_ocr_json={"source": "azure_di"}
        )
        
        assert payload.header.certificate_number == "TEST-001"
        assert len(payload.items) == 1
