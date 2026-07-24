from __future__ import annotations

from datetime import date

from .models import FinancialProviderResult, FinancialProviderStatus
from .protocol import FinancialProviderProtocol


class UnconfiguredFinancialProvider(FinancialProviderProtocol):
    """Provider state when no credentials or config are available."""
    provider_name = "unconfigured_financial"
    status = FinancialProviderStatus.UNCONFIGURED.value

    def load(self, *, as_of: date) -> FinancialProviderResult:
        return FinancialProviderResult(
            status=FinancialProviderStatus.UNCONFIGURED,
            records=(),
            as_of=as_of,
            data_gaps=("financial_data_unconfigured",),
            errors=(),
        )


class PermissionDeniedFinancialProvider(FinancialProviderProtocol):
    """Provider state when credentials authenticate but lack permissions."""
    provider_name = "permission_denied_financial"
    status = FinancialProviderStatus.PERMISSION_DENIED.value

    def load(self, *, as_of: date) -> FinancialProviderResult:
        return FinancialProviderResult(
            status=FinancialProviderStatus.PERMISSION_DENIED,
            records=(),
            as_of=as_of,
            data_gaps=("financial_data_permission_denied",),
            errors=("api_permission_denied",),
        )


class UpstreamUnavailableFinancialProvider(FinancialProviderProtocol):
    """Provider state when the upstream service is unreachable."""
    provider_name = "upstream_unavailable_financial"
    status = FinancialProviderStatus.UPSTREAM_UNAVAILABLE.value

    def load(self, *, as_of: date) -> FinancialProviderResult:
        return FinancialProviderResult(
            status=FinancialProviderStatus.UPSTREAM_UNAVAILABLE,
            records=(),
            as_of=as_of,
            data_gaps=("financial_data_upstream_unavailable",),
            errors=("upstream_connection_failed",),
        )


class MalformedResponseFinancialProvider(FinancialProviderProtocol):
    """Provider state when upstream returns unparseable data."""
    provider_name = "malformed_response_financial"
    status = FinancialProviderStatus.MALFORMED_RESPONSE.value

    def load(self, *, as_of: date) -> FinancialProviderResult:
        return FinancialProviderResult(
            status=FinancialProviderStatus.MALFORMED_RESPONSE,
            records=(),
            as_of=as_of,
            data_gaps=("financial_data_malformed_response",),
            errors=("upstream_malformed_response",),
        )


class FutureRecordRejectedProvider(FinancialProviderProtocol):
    """Fixture provider that returns records with future availability.

    This provider is used to test that records whose ``available_at``
    is after ``as_of`` are properly rejected by consumers.
    """
    provider_name = "future_record_rejected_financial"
    status = FinancialProviderStatus.FIXTURE.value

    def load(self, *, as_of: date) -> FinancialProviderResult:
        from datetime import datetime, timezone
        return FinancialProviderResult(
            status=FinancialProviderStatus.FIXTURE,
            records=(),
            as_of=as_of,
            data_gaps=("future_financial_records_rejected",),
            errors=(),
        )
