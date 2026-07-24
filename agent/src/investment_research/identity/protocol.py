from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .models import IdentityResult


class IdentityProviderProtocol(ABC):
    """Protocol for date-effective asset/issuer identity mapping.

    Every provider must accept an explicit ``as_of`` date and return only
    mappings that were valid at that date.  Future mappings must be
    excluded.

    Implementations MUST NOT:
    - return ambiguous mappings without an ambiguity warning
    - randomly pick the first match among multiple possibilities
    - return identity gaps as empty strings
    - allow lookahead (current industry for historical dates)
    """

    @abstractmethod
    def load(self, *, as_of: date) -> IdentityResult:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def status(self) -> str:
        ...
