"""W10 — Bounded provider performance measurement.

Measures load_context() wall time for each provider scenario.
Requires no credentials; exits 0 within bounded time.
"""

from __future__ import annotations

import json
import time
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
from src.investment_research.integrations.research_provider_adapter import ResearchProviderAdapter


AS_OF = date(2025, 11, 1)
_SCENARIOS: dict[str, ResearchProviderAdapter] = {
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


def measure_all(trials: int = 3) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, adapter in _SCENARIOS.items():
        times: list[float] = []
        last_obs = 0
        for _ in range(trials):
            t0 = time.perf_counter()
            ctx = adapter.load_context(as_of=AS_OF)
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            last_obs = len(ctx.financial_observations)
        avg = sum(times) / len(times)
        results[name] = {
            "trials": trials,
            "mean_seconds": round(avg, 4),
            "min_seconds": round(min(times), 4),
            "max_seconds": round(max(times), 4),
            "financial_observations": last_obs,
        }
    return results


def main() -> None:
    parser = ArgumentParser(description="Measure provider load_context() performance")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per scenario")
    args = parser.parse_args()

    results = measure_all(trials=args.trials)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"=== Provider Performance ({args.trials} trials each) ===")
        for name, r in results.items():
            print(f"  {name:40s}  avg={r['mean_seconds']:.4f}s  "
                  f"min={r['min_seconds']:.4f}s  max={r['max_seconds']:.4f}s  "
                  f"obs={r['financial_observations']}")
        print("\nDone.")


if __name__ == "__main__":
    main()
