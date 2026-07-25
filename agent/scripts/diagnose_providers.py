"""W8 — Safe provider diagnostic without side effects.

Usage:
    python scripts/diagnose_providers.py [--json]
    
Exits 0 if all providers reachable, non-zero otherwise.
Outputs structured diagnostics: provenance, evidence counts, gaps.
"""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from datetime import date
from typing import Any

from src.investment_research.financials.fixture_provider import FixtureFinancialProvider
from src.investment_research.financials.error_providers import (
    UnconfiguredFinancialProvider,
    PermissionDeniedFinancialProvider,
    UpstreamUnavailableFinancialProvider,
    MalformedResponseFinancialProvider,
)
from src.investment_research.events.fixture_provider import FixtureEventProvider
from src.investment_research.events.error_providers import (
    UnconfiguredEventProvider,
    PermissionDeniedEventProvider,
)
from src.investment_research.identity.fixture_provider import FixtureIdentityProvider
from src.investment_research.identity.error_providers import (
    UnconfiguredIdentityProvider,
    PermissionDeniedIdentityProvider,
)
from src.investment_research.sectors.fixture_provider import FixtureSectorMembershipProvider
from src.investment_research.sectors.error_providers import (
    UnconfiguredSectorProvider,
    CurrentMembershipBackfillGuardProvider,
)
from src.investment_research.integrations.research_provider_adapter import (
    Provenance,
    ResearchProviderAdapter,
)


AS_OF = date(2025, 11, 1)


def _provenance_to_dict(provenance: Any) -> dict[str, str]:
    return {
        "category": provenance.category.value if provenance.category else None,
        "provider": provenance.provider_name,
    }


def diagnose_agent_configuration() -> dict[str, Any]:
    scenarios = {
        "all_fixture": ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        ),
        "financial_unconfigured": ResearchProviderAdapter(
            financial_provider=UnconfiguredFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        ),
        "financial_permission_denied": ResearchProviderAdapter(
            financial_provider=PermissionDeniedFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        ),
        "financial_upstream_unavailable": ResearchProviderAdapter(
            financial_provider=UpstreamUnavailableFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        ),
        "financial_malformed": ResearchProviderAdapter(
            financial_provider=MalformedResponseFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        ),
        "all_unconfigured": ResearchProviderAdapter(
            financial_provider=UnconfiguredFinancialProvider(),
            event_provider=UnconfiguredEventProvider(),
            identity_provider=UnconfiguredIdentityProvider(),
            sector_provider=UnconfiguredSectorProvider(),
        ),
        "event_permission_denied": ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            event_provider=PermissionDeniedEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=CurrentMembershipBackfillGuardProvider(),
        ),
        "identity_permission_denied": ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=PermissionDeniedIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        ),
    }

    results: dict[str, Any] = {}
    for name, adapter in scenarios.items():
        try:
            ctx = adapter.load_context(as_of=AS_OF)
            results[name] = {
                "status": "ok",
                "financial_observations": len(ctx.financial_observations),
                "data_gaps": len(ctx.data_gaps),
                "provenance": {
                    "financial": _provenance_to_dict(ctx.financial_provenance),
                    "events": _provenance_to_dict(ctx.event_provenance),
                    "identity": _provenance_to_dict(ctx.identity_provenance),
                    "sector": _provenance_to_dict(ctx.sector_provenance),
                },
            }
        except Exception as exc:
            results[name] = {"status": "error", "error": str(exc)}

    all_ok = all(r["status"] == "ok" for r in results.values())
    return {"all_ok": all_ok, "scenarios": results, "as_of": str(AS_OF)}


def main() -> None:
    parser = ArgumentParser(description="Diagnose provider configuration")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    result = diagnose_agent_configuration()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"=== Provider Diagnosis (as_of={AS_OF}) ===")
        for name, scenario in result["scenarios"].items():
            s = scenario["status"]
            print(f"  [{s.upper():>4}] {name}")
            if s == "ok":
                print(f"         fin_obs={scenario['financial_observations']} "
                      f"gaps={scenario['data_gaps']}")
                for prov, p in scenario["provenance"].items():
                    print(f"         {prov}: {p['category']} ({p['provider']})")
            else:
                print(f"         ERROR: {scenario.get('error', 'unknown')}")
        print(f"\nOverall: {'ALL OK' if result['all_ok'] else 'FAILURES DETECTED'}")

    sys.exit(0 if result["all_ok"] else 1)


if __name__ == "__main__":
    main()
