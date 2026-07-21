"""One-shot, opt-in delivery of an already generated daily research report."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config.accessor import get_env_config
from src.config.paths import get_data_dir
from src.investment_research.operations.delivery import (
    DailyNotificationPlanner,
    DryRunTransport,
    FeishuWebhookTransport,
    OutboxDispatcher,
    SMTPTransport,
)
from src.investment_research.operations.models import DeliveryChannel
from src.investment_research.repositories.sqlite_intelligence import SQLiteIntelligenceRepository
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--report-mode", choices=("shadow", "research"), default=None)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    config = get_env_config()
    delivery = config.research_delivery
    if delivery.mode == "disabled":
        print("Research delivery is disabled.")
        return 0
    configured_path = config.paths.vibe_investment_research_db_path.strip()
    database_path = Path(configured_path).expanduser() if configured_path else get_data_dir() / "investment_research_v2.sqlite3"
    intelligence = SQLiteIntelligenceRepository(database_path)
    operations = SQLiteOperationsRepository(database_path)
    report_mode = args.report_mode or (
        "shadow" if config.agent_tuning.vibe_investment_research_shadow_mode else "research"
    )
    report_date = args.date or datetime.now(timezone.utc).astimezone(ZoneInfo(delivery.run_timezone)).date()
    report = intelligence.get_daily_research_report(report_date, report_mode)
    now = datetime.now(timezone.utc)
    transports = {}
    channels: list[DeliveryChannel] = []
    if delivery.mode == "dry_run":
        channels = [DeliveryChannel.FEISHU, DeliveryChannel.EMAIL]
        transports = {channel: DryRunTransport() for channel in channels}
    else:
        if delivery.feishu_webhook_url:
            channels.append(DeliveryChannel.FEISHU)
            transports[DeliveryChannel.FEISHU] = FeishuWebhookTransport(delivery.feishu_webhook_url)
        if delivery.smtp_username and delivery.smtp_authorization_code and delivery.smtp_recipient:
            channels.append(DeliveryChannel.EMAIL)
            transports[DeliveryChannel.EMAIL] = SMTPTransport(
                delivery.smtp_host,
                delivery.smtp_port,
                delivery.smtp_username,
                delivery.smtp_authorization_code,
                delivery.smtp_recipient,
            )
        if not channels:
            raise RuntimeError("live delivery has no fully configured channel")
    inserted = DailyNotificationPlanner(operations).enqueue(report, tuple(channels), now)
    delivered, failed = OutboxDispatcher(operations, transports).dispatch_due(now)
    print(f"Database: {database_path}")
    print(f"Outbox inserted: {inserted}; delivered: {delivered}; failed: {failed}; mode: {delivery.mode}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
