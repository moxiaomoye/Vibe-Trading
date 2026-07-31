from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .models import FinancialProviderResult


class FinancialProviderProtocol(ABC):
    """Protocol for point-in-time financial data providers.

    Every provider must accept an explicit ``as_of`` date and reject any
    record whose ``available_at`` falls after it.  Records whose
    ``report_period`` ends after ``as_of`` are also rejected.

    Implementations MUST NOT:
    - guess field meanings
    - substitute the latest report for a missing historical one
    - replace missing values with 0
    - call real networks in automated tests
    - expose credentials in output
    """

    @abstractmethod
    def load(self, *, as_of: date) -> FinancialProviderResult:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def status(self) -> str:
        ...
