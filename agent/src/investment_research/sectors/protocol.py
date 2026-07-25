from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .models import SectorMembershipResult


class SectorMembershipProviderProtocol(ABC):
    """Protocol for date-effective sector membership data.

    Every provider must accept an explicit ``as_of`` date and return only
    memberships that were valid at that date.

    Implementations MUST NOT:
    - return current memberships as historical memberships
    - substitute relative_to_market when sector data is unavailable
    - delete candidates due to missing sector data
    - use today's sector classification for historical dates
    """

    @abstractmethod
    def load(self, *, as_of: date) -> SectorMembershipResult:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def status(self) -> str:
        ...
