"""
Unit tests for MIDA Matcher Service.

Tests cover:
- Text normalization
- UOM normalization and compatibility
- Exact matching
- Fuzzy matching
- Insufficient quantity warnings
- UOM mismatch warnings
- Near-limit warnings
- Deterministic tie-breaking
- 1-to-1 matching (no reuse of MIDA items)
"""

from decimal import Decimal

import pytest

from app.services.mida_matcher import (
    InvoiceItem,
    MatchingResult,
    MatchMode,
    MatchResult,
    MatchWarning,
    MidaItem,
    WarningSeverity,
    are_uoms_compatible,
    calculate_similarity,
    match_items,
    normalize,
    normalize_uom,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_mida_items() -> list[MidaItem]:
    """Sample MIDA certificate items for testing."""
    return [
        MidaItem(
            line_no=1,
            item_name="COMPUTER PROCESSING UNIT",
            hs_code="84715000",
            approved_quantity=Decimal("500"),
            uom="UNIT",
        ),
        MidaItem(
            line_no=2,
            item_name="NETWORK ROUTER DEVICE",
            hs_code="85176290",
            approved_quantity=Decimal("100"),
            uom="UNIT",
        ),
        MidaItem(
            line_no=3,
            item_name="COPPER WIRE CABLE",
            hs_code="85441100",
            approved_quantity=Decimal("1000"),
            uom="KGM",
        ),
        MidaItem(
            line_no=4,
            item_name="STEEL PLATE",
            hs_code="72101200",
            approved_quantity=Decimal("5000"),
            uom="KGM",
        ),
    ]


@pytest.fixture
def sample_invoice_items() -> list[InvoiceItem]:
    """Sample invoice items for testing."""
    return [
        InvoiceItem(
            line_no=1,
            item_name="Computer Processing Unit",
            quantity=Decimal("50"),
            quantity_uom="UNT",
            net_weight=Decimal("25"),
            amount_usd=Decimal("5000"),
        ),
        InvoiceItem(
            line_no=2,
            item_name="Network Router",
            quantity=Decimal("10"),
            quantity_uom="PCS",
            net_weight=Decimal("5"),
            amount_usd=Decimal("2000"),
        ),
    ]


# =============================================================================
# Normalization Tests
# =============================================================================


class TestNormalize:
    """Tests for text normalization."""

    def test_normalize_lowercase(self):
        """Test that text is lowercased."""
        assert normalize("HELLO WORLD") == "hello world"

    def test_normalize_punctuation(self):
        """Test that punctuation is stripped."""
        assert normalize("hello, world!") == "hello world"
        assert normalize("item-name (test)") == "item name test"

    def test_normalize_spaces(self):
        """Test that multiple spaces are collapsed."""
        assert normalize("hello    world") == "hello world"
        assert normalize("  hello  world  ") == "hello world"

    def test_normalize_unicode(self):
        """Test that unicode is normalized."""
        # NFKD normalization converts ® to separate characters
        result = normalize("Item®")
        assert "item" in result

    def test_normalize_empty(self):
        """Test empty string handling."""
        assert normalize("") == ""
        assert normalize("   ") == ""

    def test_normalize_complex(self):
        """Test complex normalization."""
        assert normalize("COMPUTER PROCESSING UNIT (CPU)") == "computer processing unit cpu"
        assert normalize("Network-Router, Model: X100") == "network router model x100"


class TestNormalizeUom:
    """Tests for UOM normalization."""

    def test_normalize_unit_variants(self):
        """Test unit variants normalize to UNIT."""
        assert normalize_uom("UNT") == "UNIT"
        assert normalize_uom("pcs") == "UNIT"
        assert normalize_uom("PIECES") == "UNIT"
        assert normalize_uom("ea") == "UNIT"

    def test_normalize_kg_variants(self):
        """Test kilogram variants normalize to KGM."""
        assert normalize_uom("KGM") == "KGM"
        assert normalize_uom("kgs") == "KGM"
        assert normalize_uom("kg") == "KGM"
        assert normalize_uom("kilogram") == "KGM"

    def test_normalize_unknown_uom(self):
        """Test unknown UOM is uppercased."""
        assert normalize_uom("xyz") == "XYZ"
        assert normalize_uom("Custom") == "CUSTOM"

    def test_normalize_empty_uom(self):
        """Test empty UOM defaults to UNIT."""
        assert normalize_uom("") == "UNIT"
        assert normalize_uom("  ") == "UNIT"


class TestUomCompatibility:
    """Tests for UOM compatibility checking."""

    def test_same_uom_compatible(self):
        """Test same UOM is compatible."""
        assert are_uoms_compatible("UNIT", "UNIT") is True
        assert are_uoms_compatible("KGM", "KGM") is True

    def test_uom_variants_compatible(self):
        """Test UOM variants are compatible."""
        assert are_uoms_compatible("UNT", "UNIT") is True
        assert are_uoms_compatible("pcs", "UNIT") is True
        assert are_uoms_compatible("kgs", "KGM") is True

    def test_different_uom_not_compatible(self):
        """Test different UOMs are not compatible."""
        assert are_uoms_compatible("UNIT", "KGM") is False
        assert are_uoms_compatible("KGM", "MTR") is False
        assert are_uoms_compatible("pcs", "kg") is False


# =============================================================================
# Similarity Tests
# =============================================================================


class TestCalculateSimilarity:
    """Tests for similarity calculation."""

    def test_exact_match(self):
        """Test exact match returns 1.0."""
        assert calculate_similarity("hello world", "hello world") == 1.0

    def test_no_match(self):
        """Test completely different strings."""
        score = calculate_similarity("abc", "xyz")
        assert score < 0.5

    def test_partial_match(self):
        """Test partial match returns intermediate score."""
        score = calculate_similarity("computer processing unit", "computer unit")
        assert 0.5 < score < 1.0

    def test_word_reorder(self):
        """Test word reordering still gives reasonable score."""
        score = calculate_similarity("computer processing unit", "processing unit computer")
        assert score > 0.6

    def test_empty_strings(self):
        """Test empty strings return 0.0."""
        assert calculate_similarity("", "hello") == 0.0
        assert calculate_similarity("hello", "") == 0.0
        assert calculate_similarity("", "") == 0.0


# =============================================================================
# Exact Match Tests
# =============================================================================


class TestExactMatching:
    """Tests for exact matching mode."""

    def test_exact_match_found(self, sample_mida_items):
        """Test exact match is found when names match exactly after normalization."""
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="COMPUTER PROCESSING UNIT",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.exact,
            threshold=1.0,
        )

        assert result.matched_count == 1
        assert result.matches[0].matched is True
        assert result.matches[0].is_exact_match is True
        assert result.matches[0].match_score == 1.0
        assert result.matches[0].mida_item.line_no == 1

    def test_exact_match_case_insensitive(self, sample_mida_items):
        """Test exact match is case-insensitive."""
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="computer processing unit",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.exact,
            threshold=1.0,
        )

        assert result.matched_count == 1
        assert result.matches[0].is_exact_match is True

    def test_exact_match_not_found(self, sample_mida_items):
        """Test no match when name differs in exact mode."""
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Computer CPU",  # Different name
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.exact,
            threshold=1.0,
        )

        assert result.matched_count == 0
        assert result.unmatched_count == 1


# =============================================================================
# Fuzzy Match Tests
# =============================================================================


class TestFuzzyMatching:
    """Tests for fuzzy matching mode."""

    def test_fuzzy_match_similar_names(self, sample_mida_items):
        """Test fuzzy match finds similar names."""
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Network Router",  # Missing "DEVICE"
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        assert result.matched_count == 1
        assert result.matches[0].matched is True
        assert result.matches[0].mida_item.line_no == 2  # Network Router Device
        assert result.matches[0].match_score > 0.5

    def test_fuzzy_match_threshold(self, sample_mida_items):
        """Test fuzzy match respects threshold."""
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Completely Different Item",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.9,  # High threshold
        )

        assert result.matched_count == 0
        assert result.unmatched_count == 1

    def test_fuzzy_prefers_better_match(self, sample_mida_items):
        """Test fuzzy matching prefers higher score."""
        # Add a similar item
        mida_items = sample_mida_items + [
            MidaItem(
                line_no=5,
                item_name="COMPUTER UNIT",  # Less similar
                hs_code="84714100",
                approved_quantity=Decimal("200"),
                uom="UNIT",
            )
        ]

        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Computer Processing Unit",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        # Should match "COMPUTER PROCESSING UNIT" (line 1), not "COMPUTER UNIT" (line 5)
        assert result.matches[0].mida_item.line_no == 1


# =============================================================================
# Quantity Warning Tests
# =============================================================================


class TestQuantityWarnings:
    """Tests for quantity-related warnings."""

    def test_exceeds_remaining_quantity(self):
        """Test warning when invoice qty exceeds remaining."""
        mida_items = [
            MidaItem(
                line_no=1,
                item_name="TEST ITEM",
                hs_code="12345678",
                approved_quantity=Decimal("50"),
                uom="UNIT",
            )
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("100"),  # Exceeds 50
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        assert result.matched_count == 1
        assert len(result.warnings) == 1
        assert result.warnings[0].reason == "Exceeds remaining approved quantity"
        assert result.warnings[0].severity == WarningSeverity.error

    def test_near_limit_warning(self):
        """Test warning when invoice qty is near limit (>=90%)."""
        mida_items = [
            MidaItem(
                line_no=1,
                item_name="TEST ITEM",
                hs_code="12345678",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            )
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("95"),  # 95% of 100
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        assert result.matched_count == 1
        assert len(result.warnings) == 1
        assert result.warnings[0].reason == "Near limit"
        assert result.warnings[0].severity == WarningSeverity.info

    def test_no_warning_when_under_limit(self):
        """Test no warning when invoice qty is well under limit."""
        mida_items = [
            MidaItem(
                line_no=1,
                item_name="TEST ITEM",
                hs_code="12345678",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            )
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("50"),  # 50% of 100
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        assert result.matched_count == 1
        assert len(result.warnings) == 0


# =============================================================================
# UOM Mismatch Tests
# =============================================================================


class TestUomMismatch:
    """Tests for UOM mismatch warnings."""

    def test_uom_mismatch_warning(self):
        """Test warning when UOMs are incompatible."""
        mida_items = [
            MidaItem(
                line_no=1,
                item_name="TEST ITEM",
                hs_code="12345678",
                approved_quantity=Decimal("100"),
                uom="KGM",  # Kilograms
            )
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("50"),
                quantity_uom="UNIT",  # Units - incompatible with KGM
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        assert result.matched_count == 1
        assert len(result.warnings) == 1
        assert result.warnings[0].reason == "UOM mismatch"
        assert result.warnings[0].severity == WarningSeverity.warning

    def test_compatible_uom_variants(self):
        """Test no warning when UOM variants are compatible."""
        mida_items = [
            MidaItem(
                line_no=1,
                item_name="TEST ITEM",
                hs_code="12345678",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            )
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("50"),
                quantity_uom="pcs",  # "pcs" normalizes to UNIT
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        assert result.matched_count == 1
        # No UOM mismatch warning
        uom_warnings = [w for w in result.warnings if w.reason == "UOM mismatch"]
        assert len(uom_warnings) == 0


# =============================================================================
# Tie-Breaking Tests
# =============================================================================


class TestTieBreaking:
    """Tests for deterministic tie-breaking."""

    def test_prefer_exact_over_fuzzy(self):
        """Test that exact matches are preferred over fuzzy."""
        mida_items = [
            MidaItem(
                line_no=1,
                item_name="TEST ITEM ABC",
                hs_code="11111111",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            ),
            MidaItem(
                line_no=2,
                item_name="TEST ITEM",  # Exact match
                hs_code="22222222",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            ),
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        # Should match line 2 (exact match) over line 1 (fuzzy)
        assert result.matches[0].mida_item.line_no == 2
        assert result.matches[0].is_exact_match is True

    def test_prefer_lower_line_no_on_tie(self):
        """Test that lower line_no is preferred when scores are equal."""
        mida_items = [
            MidaItem(
                line_no=5,
                item_name="TEST ITEM",
                hs_code="55555555",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            ),
            MidaItem(
                line_no=2,
                item_name="TEST ITEM",  # Same name, lower line_no
                hs_code="22222222",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            ),
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            )
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.exact,
            threshold=1.0,
        )

        # Should match line 2 (lower line_no)
        assert result.matches[0].mida_item.line_no == 2


# =============================================================================
# 1-to-1 Matching Tests
# =============================================================================


class TestOneToOneMatching:
    """Tests for 1-to-1 matching (no MIDA item reuse)."""

    def test_no_mida_item_reuse(self):
        """Test that each MIDA item is only matched once."""
        mida_items = [
            MidaItem(
                line_no=1,
                item_name="TEST ITEM",
                hs_code="12345678",
                approved_quantity=Decimal("100"),
                uom="UNIT",
            )
        ]
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Test Item",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            ),
            InvoiceItem(
                line_no=2,
                item_name="Test Item",  # Same name as line 1
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            ),
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=mida_items,
            mode=MatchMode.exact,
            threshold=1.0,
        )

        # First invoice item matches, second doesn't (MIDA item already used)
        assert result.matched_count == 1
        assert result.unmatched_count == 1
        assert result.matches[0].matched is True
        assert result.matches[1].matched is False

    def test_multiple_matches_different_items(self, sample_mida_items):
        """Test multiple invoice items match different MIDA items."""
        invoice_items = [
            InvoiceItem(
                line_no=1,
                item_name="Computer Processing Unit",
                quantity=Decimal("10"),
                quantity_uom="UNIT",
            ),
            InvoiceItem(
                line_no=2,
                item_name="Network Router Device",
                quantity=Decimal("5"),
                quantity_uom="UNIT",
            ),
        ]

        result = match_items(
            invoice_items=invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.exact,
            threshold=1.0,
        )

        assert result.matched_count == 2
        # Each matched to different MIDA items
        matched_lines = {m.mida_item.line_no for m in result.matches if m.matched}
        assert matched_lines == {1, 2}


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests with realistic data."""

    def test_full_matching_workflow(self, sample_mida_items, sample_invoice_items):
        """Test complete matching workflow."""
        result = match_items(
            invoice_items=sample_invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        assert result.total_invoice_items == 2
        assert result.matched_count == 2
        assert result.unmatched_count == 0

        # Check remaining quantities are updated
        for match in result.matches:
            if match.matched:
                assert match.remaining_qty >= Decimal(0)

    def test_stable_results(self, sample_mida_items, sample_invoice_items):
        """Test that matching produces stable, deterministic results."""
        result1 = match_items(
            invoice_items=sample_invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )
        result2 = match_items(
            invoice_items=sample_invoice_items,
            mida_items=sample_mida_items,
            mode=MatchMode.fuzzy,
            threshold=0.5,
        )

        # Results should be identical
        assert result1.matched_count == result2.matched_count
        for m1, m2 in zip(result1.matches, result2.matches):
            if m1.matched and m2.matched:
                assert m1.mida_item.line_no == m2.mida_item.line_no
                assert m1.match_score == m2.match_score
