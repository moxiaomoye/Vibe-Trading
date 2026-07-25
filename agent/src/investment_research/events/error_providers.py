from __future__ import annotations

from datetime import date

from .models import EventProviderResult, EventProviderStatus
from .protocol import EventProviderProtocol


class UnconfiguredEventProvider(EventProviderProtocol):
    provider_name = "unconfigured_event"
    status = EventProviderStatus.UNCONFIGURED.value

    def load(self, *, as_of: date) -> EventProviderResult:
        return EventProviderResult(
            status=EventProviderStatus.UNCONFIGURED,
            records=(),
            as_of=as_of,
            data_gaps=("event_data_unconfigured",),
            errors=(),
        )


class PermissionDeniedEventProvider(EventProviderProtocol):
    provider_name = "permission_denied_event"
    status = EventProviderStatus.PERMISSION_DENIED.value

    def load(self, *, as_of: date) -> EventProviderResult:
        return EventProviderResult(
            status=EventProviderStatus.PERMISSION_DENIED,
            records=(),
            as_of=as_of,
            data_gaps=("event_data_permission_denied",),
            errors=("api_permission_denied",),
        )


class UpstreamUnavailableEventProvider(EventProviderProtocol):
    provider_name = "upstream_unavailable_event"
    status = EventProviderStatus.UPSTREAM_UNAVAILABLE.value

    def load(self, *, as_of: date) -> EventProviderResult:
        return EventProviderResult(
            status=EventProviderStatus.UPSTREAM_UNAVAILABLE,
            records=(),
            as_of=as_of,
            data_gaps=("event_data_upstream_unavailable",),
            errors=("upstream_connection_failed",),
        )


class MalformedResponseEventProvider(EventProviderProtocol):
    provider_name = "malformed_response_event"
    status = EventProviderStatus.MALFORMED_RESPONSE.value

    def load(self, *, as_of: date) -> EventProviderResult:
        return EventProviderResult(
            status=EventProviderStatus.MALFORMED_RESPONSE,
            records=(),
            as_of=as_of,
            data_gaps=("event_data_malformed_response",),
            errors=("upstream_malformed_response",),
        )


class FuturePublicationRejectedProvider(EventProviderProtocol):
    provider_name = "future_publication_rejected_event"
    status = EventProviderStatus.FIXTURE.value

    def load(self, *, as_of: date) -> EventProviderResult:
        return EventProviderResult(
            status=EventProviderStatus.FIXTURE,
            records=(),
            as_of=as_of,
            data_gaps=("future_event_publications_rejected",),
            errors=(),
        )
