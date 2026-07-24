from __future__ import annotations

from datetime import date

from .models import IdentityProviderStatus, IdentityResult
from .protocol import IdentityProviderProtocol


class UnconfiguredIdentityProvider(IdentityProviderProtocol):
    provider_name = "unconfigured_identity"
    status = IdentityProviderStatus.UNCONFIGURED.value

    def load(self, *, as_of: date) -> IdentityResult:
        return IdentityResult(
            status=IdentityProviderStatus.UNCONFIGURED,
            issuers=(), securities=(), as_of=as_of,
            data_gaps=("identity_data_unconfigured",),
            errors=(), ambiguity_warnings=(),
        )


class PermissionDeniedIdentityProvider(IdentityProviderProtocol):
    provider_name = "permission_denied_identity"
    status = IdentityProviderStatus.PERMISSION_DENIED.value

    def load(self, *, as_of: date) -> IdentityResult:
        return IdentityResult(
            status=IdentityProviderStatus.PERMISSION_DENIED,
            issuers=(), securities=(), as_of=as_of,
            data_gaps=("identity_data_permission_denied",),
            errors=("api_permission_denied",),
            ambiguity_warnings=(),
        )


class UpstreamUnavailableIdentityProvider(IdentityProviderProtocol):
    provider_name = "upstream_unavailable_identity"
    status = IdentityProviderStatus.UPSTREAM_UNAVAILABLE.value

    def load(self, *, as_of: date) -> IdentityResult:
        return IdentityResult(
            status=IdentityProviderStatus.UPSTREAM_UNAVAILABLE,
            issuers=(), securities=(), as_of=as_of,
            data_gaps=("identity_data_upstream_unavailable",),
            errors=("upstream_connection_failed",),
            ambiguity_warnings=(),
        )


class FutureMappingRejectedProvider(IdentityProviderProtocol):
    provider_name = "future_mapping_rejected_identity"
    status = IdentityProviderStatus.FIXTURE.value

    def load(self, *, as_of: date) -> IdentityResult:
        return IdentityResult(
            status=IdentityProviderStatus.FIXTURE,
            issuers=(), securities=(), as_of=as_of,
            data_gaps=("future_mappings_rejected",),
            errors=(), ambiguity_warnings=(),
        )
