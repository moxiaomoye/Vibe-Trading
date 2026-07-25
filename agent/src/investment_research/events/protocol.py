from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .models import EventProviderResult


class EventProviderProtocol(ABC):
    """Protocol for point-in-time announcement/event data providers.

    Every provider must accept an explicit ``as_of`` date and reject any
    record whose ``availability_time`` falls after it.

    Implementations MUST NOT:
    - return unauthenticated data as authenticated announcements
    - guess API endpoint paths or signature algorithms
    - send placeholder signatures to real services
    - expose credentials in source_url or output
    - replace missing body data with filler
    """

    @abstractmethod
    def load(self, *, as_of: date) -> EventProviderResult:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def status(self) -> str:
        ...
