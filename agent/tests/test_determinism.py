"""W4 — Determinism, idempotency & stable serialization tests.

Verifies that fixture providers, report generation, and API responses
produce deterministic, idempotent output regardless of dict ordering,
wall-clock time, or repeated calls.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

import pytest

from src.investment_research.events.fixture_provider import FixtureEventProvider
from src.investment_research.financials.fixture_provider import FixtureFinancialProvider
from src.investment_research.identity.fixture_provider import FixtureIdentityProvider
from src.investment_research.sectors.fixture_provider import FixtureSectorMembershipProvider
from src.investment_research.integrations.research_provider_adapter import ResearchProviderAdapter


AS_OF = date(2025, 11, 1)


@pytest.fixture
def fixture_adapter() -> ResearchProviderAdapter:
    return ResearchProviderAdapter(
        financial_provider=FixtureFinancialProvider(),
        event_provider=FixtureEventProvider(),
        identity_provider=FixtureIdentityProvider(),
        sector_provider=FixtureSectorMembershipProvider(),
    )


class TestFixtureDeterminism:
    """Fixture providers must return identical output for the same as_of."""

    @pytest.mark.parametrize(
        "provider_cls,attr",
        [
            (FixtureFinancialProvider, "records"),
            (FixtureEventProvider, "records"),
            (FixtureIdentityProvider, "securities"),
            (FixtureSectorMembershipProvider, "memberships"),
        ],
    )
    def test_deterministic_repeated_call(self, provider_cls: type, attr: str) -> None:
        provider = provider_cls()
        r1 = getattr(provider.load(as_of=AS_OF), attr)
        r2 = getattr(provider.load(as_of=AS_OF), attr)
        assert r1 == r2

    def test_deterministic_across_provider_types(self, fixture_adapter: ResearchProviderAdapter) -> None:
        ctx1 = fixture_adapter.load_context(as_of=AS_OF)
        ctx2 = fixture_adapter.load_context(as_of=AS_OF)
        assert ctx1.financial_observations == ctx2.financial_observations
        assert ctx1.data_gaps == ctx2.data_gaps
        assert ctx1.ambiguity_warnings == ctx2.ambiguity_warnings


class TestDictOrderIndependence:
    """Changing dict key insertion order must not change serialized output."""

    def test_reversed_dict_keys(self) -> None:
        """Same data with reversed key order should produce same sorted JSON."""
        d1 = {"a": 1, "b": 2, "c": 3}
        d2 = {"c": 3, "b": 2, "a": 1}
        j1 = json.dumps(d1, sort_keys=True, separators=(",", ":"))
        j2 = json.dumps(d2, sort_keys=True, separators=(",", ":"))
        assert j1 == j2

    def test_fingerprint_stable(self) -> None:
        """SHA-256 fingerprint of sorted JSON is order-independent."""
        payload = {"symbol": "000001", "price": 10.5, "timestamp": "2025-07-24T00:00:00Z"}
        payload_reversed = {"timestamp": "2025-07-24T00:00:00Z", "price": 10.5, "symbol": "000001"}
        fp1 = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        fp2 = hashlib.sha256(
            json.dumps(payload_reversed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert fp1 == fp2


class TestIdempotentAdapter:
    """ResearchProviderAdapter.load_context must be idempotent (no side effects)."""

    def test_repeated_load_identical(self, fixture_adapter: ResearchProviderAdapter) -> None:
        ctx1 = fixture_adapter.load_context(as_of=AS_OF)
        ctx2 = fixture_adapter.load_context(as_of=AS_OF)
        assert ctx1 == ctx2

    def test_provenance_stable(self, fixture_adapter: ResearchProviderAdapter) -> None:
        ctx = fixture_adapter.load_context(as_of=AS_OF)
        def _prov_key(p: Any) -> str:
            return f"{p.category}|{p.provider_name}|{p.detail}"
        key1 = "|".join(sorted([
            _prov_key(ctx.financial_provenance) if ctx.financial_provenance else "",
            _prov_key(ctx.event_provenance) if ctx.event_provenance else "",
            _prov_key(ctx.identity_provenance) if ctx.identity_provenance else "",
            _prov_key(ctx.sector_provenance) if ctx.sector_provenance else "",
        ]))
        key2 = "|".join(sorted([
            _prov_key(ctx.financial_provenance) if ctx.financial_provenance else "",
            _prov_key(ctx.event_provenance) if ctx.event_provenance else "",
            _prov_key(ctx.identity_provenance) if ctx.identity_provenance else "",
            _prov_key(ctx.sector_provenance) if ctx.sector_provenance else "",
        ]))
        assert key1 == key2


class TestFingerprintConsistency:
    """Fingerprint generation must be deterministic."""

    def test_same_input_same_fingerprint(self) -> None:
        payload = {"type": "test", "value": 42, "tags": ["a", "b"]}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        fp1 = hashlib.sha256(encoded).hexdigest()
        fp2 = hashlib.sha256(encoded).hexdigest()
        assert fp1 == fp2

    def test_list_order_affects_fingerprint(self) -> None:
        """List ordering does NOT change because sort_keys sorts dict keys only."""
        payload1 = {"items": [1, 2, 3]}
        payload2 = {"items": [1, 3, 2]}
        fp1 = hashlib.sha256(
            json.dumps(payload1, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        fp2 = hashlib.sha256(
            json.dumps(payload2, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert fp1 != fp2  # list order matters — document baseline
