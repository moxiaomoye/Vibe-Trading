from __future__ import annotations

from datetime import date, datetime, timezone

from .models import (
    BoardType,
    Exchange,
    IdentityProviderStatus,
    IdentityResult,
    Issuer,
    SecurityIdentity,
)
from .protocol import IdentityProviderProtocol


class FixtureIdentityProvider(IdentityProviderProtocol):
    """Fixture identity provider with diverse A-share scenarios.

    Covers: SSE main board, SZSE main board, STAR, ChiNext, BSE,
    ST naming, name change, suspension, delisting, missing issuer,
    duplicate mapping, historical industry, and future mapping.
    """

    provider_name = "fixture_identity"
    status = IdentityProviderStatus.FIXTURE.value

    def __init__(self) -> None:
        self._issuers = (
            Issuer("issuer_600519", "贵州茅台", "贵州茅台酒股份有限公司"),
            Issuer("issuer_002371", "北方华创", "北方华创科技集团股份有限公司"),
            Issuer("issuer_300750", "宁德时代", "宁德时代新能源科技股份有限公司"),
            Issuer("issuer_688981", "中芯国际", "中芯国际集成电路制造有限公司"),
            Issuer("issuer_000858", "五粮液", "宜宾五粮液股份有限公司"),
            Issuer("issuer_600522", "中天科技", "江苏中天科技股份有限公司"),
            Issuer("issuer_sh_delisted", "退市公司", "退市股份有限公司"),
            Issuer("issuer_suspended", "停牌公司", "停牌股份有限公司"),
        )
        self._securities = (
            # SSE main board
            SecurityIdentity(
                normalized_symbol="600519.SH", raw_symbol="600519",
                security_code="600519", security_name="贵州茅台",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_600519", issuer_name="贵州茅台",
                listing_date=date(2001, 8, 27), delisting_date=None,
                is_st=False, effective_from=date(2001, 8, 27), effective_to=None,
                availability_time=datetime(2001, 8, 27, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # SZSE main board
            SecurityIdentity(
                normalized_symbol="002371.SZ", raw_symbol="002371",
                security_code="002371", security_name="北方华创",
                exchange=Exchange.SZSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_002371", issuer_name="北方华创",
                listing_date=date(2010, 3, 16), delisting_date=None,
                is_st=False, effective_from=date(2010, 3, 16), effective_to=None,
                availability_time=datetime(2010, 3, 16, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # ChiNext
            SecurityIdentity(
                normalized_symbol="300750.SZ", raw_symbol="300750",
                security_code="300750", security_name="宁德时代",
                exchange=Exchange.SZSE, board=BoardType.CHINEXT,
                issuer_id="issuer_300750", issuer_name="宁德时代",
                listing_date=date(2018, 6, 11), delisting_date=None,
                is_st=False, effective_from=date(2018, 6, 11), effective_to=None,
                availability_time=datetime(2018, 6, 11, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # STAR
            SecurityIdentity(
                normalized_symbol="688981.SH", raw_symbol="688981",
                security_code="688981", security_name="中芯国际",
                exchange=Exchange.SSE, board=BoardType.STAR,
                issuer_id="issuer_688981", issuer_name="中芯国际",
                listing_date=date(2020, 7, 16), delisting_date=None,
                is_st=False, effective_from=date(2020, 7, 16), effective_to=None,
                availability_time=datetime(2020, 7, 16, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # BSE
            SecurityIdentity(
                normalized_symbol="920000.BJ", raw_symbol="920000",
                security_code="920000", security_name="北交所股票",
                exchange=Exchange.BSE, board=BoardType.BEIJING,
                issuer_id="issuer_600522", issuer_name="中天科技",
                listing_date=date(2022, 1, 1), delisting_date=None,
                is_st=False, effective_from=date(2022, 1, 1), effective_to=None,
                availability_time=datetime(2022, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # Pre-ST period (original name)
            SecurityIdentity(
                normalized_symbol="600522.SH", raw_symbol="600522",
                security_code="600522", security_name="中天科技",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_600522", issuer_name="中天科技",
                listing_date=date(2002, 10, 24), delisting_date=None,
                is_st=False, effective_from=date(2002, 10, 24), effective_to=date(2025, 1, 14),
                availability_time=datetime(2002, 10, 24, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # ST period (name changed)
            SecurityIdentity(
                normalized_symbol="600522.SH", raw_symbol="600522",
                security_code="600522", security_name="ST中天",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_600522", issuer_name="中天科技",
                listing_date=date(2002, 10, 24), delisting_date=None,
                is_st=True, effective_from=date(2025, 1, 15), effective_to=date(2025, 6, 15),
                availability_time=datetime(2025, 1, 15, 17, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.1.0",
            ),
            # ST removal (name restored)
            SecurityIdentity(
                normalized_symbol="600522.SH", raw_symbol="600522",
                security_code="600522", security_name="中天科技",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_600522", issuer_name="中天科技",
                listing_date=date(2002, 10, 24), delisting_date=None,
                is_st=False, effective_from=date(2025, 6, 16), effective_to=None,
                availability_time=datetime(2025, 6, 16, 17, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.2.0",
            ),
            # Delisted
            SecurityIdentity(
                normalized_symbol="600001.SH", raw_symbol="600001",
                security_code="600001", security_name="退市股票",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_sh_delisted", issuer_name="退市公司",
                listing_date=date(2000, 1, 1), delisting_date=date(2024, 12, 31),
                is_st=False, effective_from=date(2000, 1, 1), effective_to=date(2024, 12, 31),
                availability_time=datetime(2000, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # Suspended
            SecurityIdentity(
                normalized_symbol="600002.SH", raw_symbol="600002",
                security_code="600002", security_name="停牌股票",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_suspended", issuer_name="停牌公司",
                listing_date=date(2010, 1, 1), delisting_date=None,
                is_st=False, effective_from=date(2010, 1, 1), effective_to=None,
                availability_time=datetime(2010, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
            # Name change
            SecurityIdentity(
                normalized_symbol="000858.SZ", raw_symbol="000858",
                security_code="000858", security_name="五粮液",
                exchange=Exchange.SZSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_000858", issuer_name="五粮液",
                listing_date=date(1998, 4, 27), delisting_date=None,
                is_st=False, effective_from=date(1998, 4, 27), effective_to=None,
                availability_time=datetime(1998, 4, 27, 15, 0, tzinfo=timezone.utc),
                source="fixture_identity", mapping_version="1.0.0",
            ),
        )

    def load(self, *, as_of: date) -> IdentityResult:
        gaps: list[str] = []
        errors: list[str] = []
        ambiguity: list[str] = []

        eligible = []
        for sec in self._securities:
            if sec.effective_from > as_of:
                gaps.append(f"future_mapping: {sec.normalized_symbol}")
                continue
            if sec.effective_to is not None and sec.effective_to < as_of:
                gaps.append(f"expired_mapping: {sec.normalized_symbol}")
                continue
            if sec.availability_time.date() > as_of:
                gaps.append(f"future_availability: {sec.normalized_symbol}")
                continue
            eligible.append(sec)

        # Check for duplicate effective mappings (ambiguity)
        seen: dict[str, list[str]] = {}
        for sec in eligible:
            seen.setdefault(sec.normalized_symbol, []).append(sec.security_name)
        for symbol, names in seen.items():
            if len(names) > 1:
                ambiguity.append(f"multiple_active_mappings: {symbol}")

        return IdentityResult(
            status=IdentityProviderStatus.FIXTURE,
            issuers=self._issuers,
            securities=tuple(eligible),
            as_of=as_of,
            data_gaps=tuple(gaps),
            errors=tuple(errors),
            ambiguity_warnings=tuple(ambiguity),
        )
