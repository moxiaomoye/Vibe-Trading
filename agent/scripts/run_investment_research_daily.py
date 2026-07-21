"""Generate the due AI Investment Researcher daily report and queue delivery."""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
from uuid import uuid4

from src.config.accessor import get_env_config
from src.config.paths import get_data_dir
from src.investment_research.application.daily_pipeline import DailyResearchInputs, DailyResearchPipeline
from src.investment_research.application.issuer_evidence_ingestion import IssuerEvidenceIngestionService
from src.investment_research.integrations.issuer_disclosures import SecEdgarDisclosureProvider
from src.investment_research.integrations.value_hunter_market import ValueHunterMarketAdapter
from src.investment_research.operations.models import DeliveryChannel
from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_discovery import SQLiteDiscoveryRepository
from src.investment_research.repositories.sqlite_intelligence import SQLiteIntelligenceRepository
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository
from src.investment_research.repositories.sqlite_evidence_inbox import SQLiteEvidenceInboxRepository
from src.investment_research.thesis.seeds import import_thesis_identities, load_blueprint_manifest
from src.value_hunter.providers import build_provider
from ingest_issuer_disclosures import load_subscriptions


def main() -> int:
    config = get_env_config()
    configured = config.paths.vibe_investment_research_db_path.strip()
    database_path = Path(configured).expanduser() if configured else get_data_dir() / "investment_research_v2.sqlite3"
    research = SQLiteResearchRepository(database_path)
    import_thesis_identities(research, load_blueprint_manifest(), datetime.now(timezone.utc))
    delivery = config.research_delivery
    schedule = TradingDaySchedule(
        timezone_name=delivery.run_timezone,
        run_after=time(delivery.run_hour, delivery.run_minute),
    )
    pipeline = DailyResearchPipeline(
        research,
        SQLiteIntelligenceRepository(database_path),
        SQLiteDiscoveryRepository(database_path),
        SQLiteOperationsRepository(database_path),
        schedule,
    )
    channels: list[DeliveryChannel] = []
    if delivery.mode == "dry_run":
        channels = [DeliveryChannel.FEISHU, DeliveryChannel.EMAIL]
    elif delivery.mode == "live":
        if delivery.feishu_webhook_url:
            channels.append(DeliveryChannel.FEISHU)
        if delivery.smtp_username and delivery.smtp_authorization_code and delivery.smtp_recipient:
            channels.append(DeliveryChannel.EMAIL)
    now = datetime.now(timezone.utc)
    if config.agent_tuning.vibe_investment_research_issuer_disclosures_enabled:
        subscription_value = config.paths.vibe_investment_research_issuer_subscriptions_path.strip()
        if not subscription_value:
            print("Issuer disclosure ingestion enabled without a subscription manifest; skipped.")
        else:
            inbox_service = IssuerEvidenceIngestionService(SQLiteEvidenceInboxRepository(database_path))
            disclosure_provider = SecEdgarDisclosureProvider()
            for subscription in load_subscriptions(Path(subscription_value).expanduser()):
                try:
                    result = inbox_service.ingest(disclosure_provider, subscription, now)
                    print(
                        f"Issuer evidence {result.subscription_id}: "
                        f"{result.ingested} new, {result.deduplicated} duplicate."
                    )
                except Exception as exc:
                    print(f"Issuer evidence {subscription.subscription_id} unavailable: {exc}")
    market_provider_name = config.agent_tuning.vibe_investment_research_market_provider.strip().lower()
    market_bundle = None
    if market_provider_name != "none":
        watchlist_value = config.paths.vibe_investment_research_watchlist_path.strip()
        cache_value = config.paths.vibe_investment_research_cache_dir.strip()
        watchlist_path = Path(watchlist_value).expanduser() if watchlist_value else None
        cache_dir = Path(cache_value).expanduser() if cache_value else get_data_dir() / "investment_research_cache"
        provider = build_provider(market_provider_name, watchlist_path, cache_dir)
        try:
            market_bundle = ValueHunterMarketAdapter(provider).load_with_timeout(
                now,
                config.agent_tuning.vibe_investment_research_provider_timeout_seconds,
            )
        except (RuntimeError, TimeoutError) as exc:
            print(f"Market data unavailable; daily report will declare the gap: {exc}")
    inputs = DailyResearchInputs(
        now,
        market_snapshot=market_bundle.snapshot if market_bundle else None,
        market_evidence_bundle=market_bundle.evidence_bundle if market_bundle else None,
        market_evidence=market_bundle.evidence if market_bundle else (),
    )
    report = pipeline.run_if_due(
        str(uuid4()), now, inputs,
        mode="shadow" if config.agent_tuning.vibe_investment_research_shadow_mode else "research",
        channels=tuple(channels),
    )
    if report is None:
        print("Daily research is not due or has already been claimed.")
        return 0
    print(f"Daily research report: {report.report_id}")
    print(report.conclusion)
    print("Notifications were queued; delivery is handled by deliver_investment_research.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
