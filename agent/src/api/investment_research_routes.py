"""Read-only HTTP surface for AI Investment Researcher V2."""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.optional_routes import DisabledStub, try_register_routes
from src.config.accessor import get_env_config
from src.config.paths import get_data_dir
from src.investment_research.discovery.models import DiscoveryDisposition
from src.investment_research.evidence.inbox import EvidenceInboxStatus
from src.investment_research.evidence.associations import EvidenceSubjectType
from src.investment_research.application.evidence_readiness import ThesisEvidenceReadinessService
from src.investment_research.application.macro_evidence_ingestion import (
    MacroEvidenceIngestionService,
)
from src.investment_research.application.manual_thesis_initialization import (
    ManualEvidenceDraft,
    ManualThesisInitializationCommand,
    ManualThesisInitializationService,
)
from src.investment_research.macro.fred_provider import FredMacroEvidenceProvider
from src.investment_research.repositories.sqlite import SCHEMA_VERSION, SQLiteResearchRepository
from src.investment_research.repositories.sqlite_discovery import SQLiteDiscoveryRepository
from src.investment_research.repositories.sqlite_evidence_inbox import (
    EVIDENCE_INBOX_SCHEMA_VERSION,
    SQLiteEvidenceInboxRepository,
)
from src.investment_research.repositories.sqlite_evidence_associations import (
    EVIDENCE_ASSOCIATION_SCHEMA_VERSION,
    SQLiteEvidenceAssociationRepository,
)
from src.investment_research.repositories.sqlite_evidence_set_reviews import (
    EVIDENCE_SET_REVIEW_SCHEMA_VERSION,
    SQLiteEvidenceSetReviewRepository,
)
from src.investment_research.repositories.sqlite_intelligence import SQLiteIntelligenceRepository
from src.investment_research.thesis.models import Thesis, ThesisVersion
from src.investment_research.operations.daily_opportunity_report import (
    DailyOpportunityReportService,
)
from src.investment_research.operations.reviewed_context import (
    ReviewedResearchContextLoader,
)
from src.investment_research.operations.daily_automation import (
    DailyOpportunityAutomation,
)
from src.investment_research.operations.delivery import (
    DryRunTransport,
    FeishuWebhookTransport,
    OpportunityReportNotificationPlanner,
    OutboxDispatcher,
    ServerChanTurboTransport,
    SMTPTransport,
)
from src.investment_research.operations.models import DeliveryChannel
from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.operations.shadow_portfolio import ShadowPortfolioTracker
from src.investment_research.operations.vibe_research import VibeResearchCoordinator
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository


AuthDep = Callable[..., Awaitable[Any] | Any]
_repository: SQLiteResearchRepository | None = None
_intelligence_repository: SQLiteIntelligenceRepository | None = None
_discovery_repository: SQLiteDiscoveryRepository | None = None
_evidence_inbox_repository: SQLiteEvidenceInboxRepository | None = None
_evidence_association_repository: SQLiteEvidenceAssociationRepository | None = None
_evidence_set_review_repository: SQLiteEvidenceSetReviewRepository | None = None
_daily_opportunity_service: DailyOpportunityReportService | None = None
_operations_repository: SQLiteOperationsRepository | None = None
_shadow_portfolio_tracker: ShadowPortfolioTracker | None = None
_daily_opportunity_automation: DailyOpportunityAutomation | None = None
_vibe_research_coordinator: VibeResearchCoordinator | None = None


class OpportunityNotificationRequest(BaseModel):
    confirm: bool = False
    channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.FEISHU, DeliveryChannel.EMAIL],
        min_length=1,
    )


class ManualThesisEvidenceRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    source_locator: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4000)
    published_at: datetime


class ManualThesisInitializationRequest(BaseModel):
    thesis_id: str = Field(min_length=1, max_length=100)
    core_claim: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[ManualThesisEvidenceRequest] = Field(
        min_length=1, max_length=10
    )
    counter_evidence: list[ManualThesisEvidenceRequest] = Field(
        min_length=1, max_length=10
    )
    catalysts: list[str] = Field(min_length=1, max_length=20)
    kill_criteria: list[str] = Field(min_length=1, max_length=20)
    next_review_days: int = Field(default=30, ge=1, le=365)
    reviewer: str = Field(min_length=1, max_length=100)
    review_rationale: str = Field(min_length=1, max_length=2000)
    confirm: bool = False


def _database_path() -> Path:
    configured = get_env_config().paths.vibe_investment_research_db_path.strip()
    return Path(configured).expanduser() if configured else get_data_dir() / "investment_research_v2.sqlite3"


def get_investment_research_repository() -> SQLiteResearchRepository:
    global _repository
    if _repository is None:
        _repository = SQLiteResearchRepository(_database_path())
    return _repository


def get_intelligence_repository() -> SQLiteIntelligenceRepository:
    global _intelligence_repository
    if _intelligence_repository is None:
        _intelligence_repository = SQLiteIntelligenceRepository(_database_path())
    return _intelligence_repository


def get_discovery_repository() -> SQLiteDiscoveryRepository:
    global _discovery_repository
    if _discovery_repository is None:
        _discovery_repository = SQLiteDiscoveryRepository(_database_path())
    return _discovery_repository


def get_evidence_inbox_repository() -> SQLiteEvidenceInboxRepository:
    global _evidence_inbox_repository
    if _evidence_inbox_repository is None:
        _evidence_inbox_repository = SQLiteEvidenceInboxRepository(_database_path())
    return _evidence_inbox_repository


def get_evidence_association_repository() -> SQLiteEvidenceAssociationRepository:
    global _evidence_association_repository
    if _evidence_association_repository is None:
        _evidence_association_repository = SQLiteEvidenceAssociationRepository(_database_path())
    return _evidence_association_repository


def get_evidence_set_review_repository() -> SQLiteEvidenceSetReviewRepository:
    global _evidence_set_review_repository
    if _evidence_set_review_repository is None:
        _evidence_set_review_repository = SQLiteEvidenceSetReviewRepository(_database_path())
    return _evidence_set_review_repository


def get_daily_opportunity_service() -> DailyOpportunityReportService:
    global _daily_opportunity_service
    if _daily_opportunity_service is None:
        _daily_opportunity_service = DailyOpportunityReportService(
            research_context_loader=ReviewedResearchContextLoader(
                get_investment_research_repository()
            ).load
        )
    return _daily_opportunity_service


def get_shadow_portfolio_tracker() -> ShadowPortfolioTracker:
    global _shadow_portfolio_tracker
    if _shadow_portfolio_tracker is None:
        _shadow_portfolio_tracker = ShadowPortfolioTracker(
            get_data_dir() / "investment-research" / "shadow-portfolio.json"
        )
    return _shadow_portfolio_tracker


def get_vibe_research_coordinator() -> VibeResearchCoordinator:
    global _vibe_research_coordinator
    if _vibe_research_coordinator is None:
        timeout_seconds = (
            get_env_config()
            .agent_tuning
            .vibe_investment_research_deep_timeout_seconds
        )
        _vibe_research_coordinator = VibeResearchCoordinator(
            get_data_dir() / "investment-research" / "vibe-deep-research.json",
            timeout_seconds=timeout_seconds,
        )
    return _vibe_research_coordinator


def get_operations_repository() -> SQLiteOperationsRepository:
    global _operations_repository
    if _operations_repository is None:
        _operations_repository = SQLiteOperationsRepository(_database_path())
    return _operations_repository


def _delivery_status() -> dict[str, Any]:
    config = get_env_config().research_delivery
    configured = {
        DeliveryChannel.FEISHU: bool(config.feishu_webhook_url.strip()),
        DeliveryChannel.EMAIL: bool(
            config.smtp_host.strip()
            and config.smtp_username.strip()
            and config.smtp_authorization_code.strip()
            and config.smtp_recipient.strip()
        ),
        DeliveryChannel.SERVERCHAN: bool(config.serverchan_send_key.strip()),
    }
    return {
        "mode": config.mode,
        "enabled": config.mode in {"dry_run", "live"},
        "manual_confirmation_required": not config.daily_automation_enabled,
        "scheduler_enabled": config.daily_automation_enabled,
        "configured_channels": [
            channel.value for channel, ready in configured.items() if ready
        ],
        "channel_status": {
            channel.value: {"configured": ready}
            for channel, ready in configured.items()
        },
        "credentials_exposed": False,
    }


def _delivery_transports(
    channels: tuple[DeliveryChannel, ...],
) -> dict[DeliveryChannel, Any]:
    config = get_env_config().research_delivery
    if config.mode == "dry_run":
        return {channel: DryRunTransport() for channel in channels}
    transports: dict[DeliveryChannel, Any] = {}
    if DeliveryChannel.FEISHU in channels and config.feishu_webhook_url.strip():
        transports[DeliveryChannel.FEISHU] = FeishuWebhookTransport(
            config.feishu_webhook_url.strip()
        )
    if DeliveryChannel.EMAIL in channels and all(
        (
            config.smtp_host.strip(),
            config.smtp_username.strip(),
            config.smtp_authorization_code.strip(),
            config.smtp_recipient.strip(),
        )
    ):
        transports[DeliveryChannel.EMAIL] = SMTPTransport(
            host=config.smtp_host.strip(),
            port=config.smtp_port,
            username=config.smtp_username.strip(),
            authorization_code=config.smtp_authorization_code.strip(),
            recipient=config.smtp_recipient.strip(),
        )
    if (
        DeliveryChannel.SERVERCHAN in channels
        and config.serverchan_send_key.strip()
    ):
        transports[DeliveryChannel.SERVERCHAN] = ServerChanTurboTransport(
            config.serverchan_send_key.strip()
        )
    return transports


def reset_investment_research_repository() -> None:
    global _repository, _intelligence_repository, _discovery_repository
    global _evidence_inbox_repository, _evidence_association_repository, _evidence_set_review_repository
    global _daily_opportunity_service, _operations_repository
    global _shadow_portfolio_tracker, _daily_opportunity_automation
    global _vibe_research_coordinator
    _repository = None
    _intelligence_repository = None
    _discovery_repository = None
    _evidence_inbox_repository = None
    _evidence_association_repository = None
    _evidence_set_review_repository = None
    _daily_opportunity_service = None
    _operations_repository = None
    _shadow_portfolio_tracker = None
    _daily_opportunity_automation = None
    _vibe_research_coordinator = None


def _as_of(value: datetime | None) -> datetime:
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise HTTPException(status_code=422, detail="as_of must include a timezone offset")
    return resolved


def _thesis_payload(thesis: Thesis, version: ThesisVersion | None) -> dict[str, Any]:
    return {
        "thesis_id": thesis.thesis_id,
        "name": thesis.name,
        "parent_thesis_id": thesis.parent_thesis_id,
        "scope": thesis.scope.value,
        "created_at": thesis.created_at.isoformat(),
        "current_version": _version_payload(version) if version else None,
        "research_state": "versioned" if version else "uninitialized",
    }


def _version_payload(version: ThesisVersion) -> dict[str, Any]:
    return {
        "thesis_version_id": version.thesis_version_id,
        "thesis_id": version.thesis_id,
        "version_number": version.version_number,
        "status": version.status.value,
        "core_claim": version.core_claim,
        "confidence": version.confidence,
        "evidence_set_id": version.evidence_set_id,
        "supporting_evidence_ids": list(version.supporting_evidence_ids),
        "counter_evidence_ids": list(version.counter_evidence_ids),
        "catalysts": list(version.catalysts),
        "kill_criteria": list(version.kill_criteria),
        "change_summary": version.change_summary,
        "effective_from": version.effective_from.isoformat(),
        "next_review_at": version.next_review_at.isoformat(),
        "supersedes_version_id": version.supersedes_version_id,
    }


def _readiness_payload(readiness: Any) -> dict[str, Any]:
    return {
        "thesis_id": readiness.thesis_id,
        "as_of": readiness.as_of.isoformat(),
        "verdict": readiness.verdict.value,
        "supporting_association_ids": list(readiness.supporting_association_ids),
        "counter_association_ids": list(readiness.counter_association_ids),
        "neutral_association_ids": list(readiness.neutral_association_ids),
        "blocking_gaps": list(readiness.blocking_gaps),
        "quality_warnings": list(readiness.quality_warnings),
        "first_rejection_question": readiness.first_rejection_question,
        "approval_review_id": readiness.approval_review_id,
    }


def _configured_delivery_channels() -> tuple[DeliveryChannel, ...]:
    config = get_env_config().research_delivery
    channels: list[DeliveryChannel] = []
    if config.feishu_webhook_url.strip():
        channels.append(DeliveryChannel.FEISHU)
    if all(
        (
            config.smtp_host.strip(),
            config.smtp_username.strip(),
            config.smtp_authorization_code.strip(),
            config.smtp_recipient.strip(),
        )
    ):
        channels.append(DeliveryChannel.EMAIL)
    if config.serverchan_send_key.strip():
        channels.append(DeliveryChannel.SERVERCHAN)
    return tuple(channels)


async def _dispatch_vibe_research(report: dict[str, Any]) -> dict[str, Any]:
    if not bool((report.get("market") or {}).get("panic")):
        return {"status": "not_required", "session_id": None, "attempt_id": None}
    host = (
        sys.modules.get("api_server")
        or sys.modules.get("agent.api_server")
        or sys.modules.get("__main__")
    )
    service = getattr(host, "_get_session_service", lambda: None)() if host else None
    if service is None:
        return {"status": "session_runtime_unavailable", "session_id": None, "attempt_id": None}
    report_date = str(report.get("report_date") or "")
    return await get_vibe_research_coordinator().dispatch(
        service,
        report_date=report_date,
        prompt=str(report.get("agent_prompt") or ""),
        title=f"每日恐慌投研 {report_date}",
    )


async def _run_daily_opportunity_automation(_now: datetime) -> dict[str, Any]:
    report = await asyncio.wait_for(
        asyncio.to_thread(get_daily_opportunity_service().run),
        timeout=90.0,
    )
    shadow = await asyncio.to_thread(get_shadow_portfolio_tracker().process, report)
    try:
        research = await _dispatch_vibe_research(report)
    except Exception as exc:
        research = {
            "status": "failed",
            "error": type(exc).__name__,
            "session_id": None,
            "attempt_id": None,
        }

    delivery = {
        "planned": 0,
        "delivered": 0,
        "failed": 0,
        "suppressed": 0,
    }
    config = get_env_config().research_delivery
    channels = _configured_delivery_channels()
    if config.mode in {"dry_run", "live"} and channels:
        try:
            repository = get_operations_repository()
            planner = OpportunityReportNotificationPlanner(
                repository,
                report_web_url=config.report_web_url,
            )
            message_ids = planner.enqueue(report, channels, datetime.now(timezone.utc))
            delivered, failed = OutboxDispatcher(
                repository,
                _delivery_transports(channels),
            ).dispatch_message_ids(message_ids, datetime.now(timezone.utc))
            delivery = {
                "planned": len(message_ids),
                "delivered": delivered,
                "failed": failed,
                "suppressed": len(message_ids) - delivered - failed,
            }
        except Exception as exc:
            delivery = {
                "planned": 0,
                "delivered": 0,
                "failed": 1,
                "suppressed": 0,
                "error": type(exc).__name__,
            }
    return {
        "report_date": report["report_date"],
        "report_fingerprint": report.get("_fingerprint"),
        "market_panic": bool((report.get("market") or {}).get("panic")),
        "vibe_research": research,
        "shadow_equity": (
            shadow.get("daily_snapshots", [{}])[-1].get("equity")
            if shadow.get("daily_snapshots")
            else shadow.get("initial_cash")
        ),
        "delivery": delivery,
        "trading_executed": False,
    }


def get_daily_opportunity_automation() -> DailyOpportunityAutomation:
    global _daily_opportunity_automation
    if _daily_opportunity_automation is None:
        config = get_env_config().research_delivery
        _daily_opportunity_automation = DailyOpportunityAutomation(
            _run_daily_opportunity_automation,
            get_data_dir() / "investment-research" / "daily-automation.json",
            schedule=TradingDaySchedule(
                timezone_name=config.run_timezone,
                run_after=clock_time(config.run_hour, config.run_minute),
            ),
            enabled=config.daily_automation_enabled,
        )
    return _daily_opportunity_automation


def register_investment_research_routes(app: FastAPI, require_auth: AuthDep) -> None:
    automation = get_daily_opportunity_automation()
    if automation.enabled:
        app.on_event("startup")(automation.start)
        app.on_event("shutdown")(automation.stop)
    try_register_routes(
        app,
        feature_name="Historical Evaluation API",
        env_var="PANIC_SHADOW_REPORT_API_ENABLED",
        module_path="src.api.historical_evaluation_routes",
        register_func_name="register_historical_evaluation_routes",
        require_auth=require_auth,
        disabled_stubs=[
            DisabledStub(
                "/investment-research/historical-evaluation/status",
                {"enabled": False, "status": "disabled", "feature": "historical_evaluation", "reason": "feature_not_enabled"},
            ),
            DisabledStub(
                "/investment-research/historical-evaluation/evaluate-auto",
                {"enabled": False, "status": "disabled", "feature": "historical_evaluation", "reason": "feature_not_enabled"},
                methods={"POST"},
                status_code=404,
            ),
            DisabledStub(
                "/investment-research/historical-evaluation/evaluate-manual",
                {"enabled": False, "status": "disabled", "feature": "historical_evaluation", "reason": "feature_not_enabled"},
                methods={"POST"},
                status_code=404,
            ),
        ],
    )
    try_register_routes(
        app,
        feature_name="Panic Shadow Report API",
        env_var="PANIC_SHADOW_REPORT_API_ENABLED",
        module_path="src.api.panic_shadow_report_routes",
        register_func_name="register_panic_shadow_report_routes",
        require_auth=require_auth,
        disabled_stubs=[
            DisabledStub("/investment-research/panic-shadow/status", {"enabled": False, "status": "disabled", "feature": "panic_shadow", "reason": "feature_not_enabled"}),
            DisabledStub("/investment-research/panic-shadow/run", {"enabled": False, "status": "disabled", "feature": "panic_shadow", "reason": "feature_not_enabled"}, methods={"POST"}, status_code=404),
            DisabledStub("/investment-research/panic-shadow/run-current", {"enabled": False, "status": "disabled", "feature": "panic_shadow", "reason": "feature_not_enabled"}, methods={"POST"}, status_code=404),
            DisabledStub("/investment-research/panic-shadow/run-manual", {"enabled": False, "status": "disabled", "feature": "panic_shadow", "reason": "feature_not_enabled"}, methods={"POST"}, status_code=404),
            DisabledStub("/investment-research/panic-shadow/latest", {"enabled": False, "status": "disabled", "feature": "panic_shadow", "reason": "feature_not_enabled"}, status_code=404),
        ],
    )
    dependencies = [Depends(require_auth)]

    @app.get("/investment-research/status", dependencies=dependencies)
    async def investment_research_status() -> dict[str, Any]:
        config = get_env_config()
        repository = get_investment_research_repository()
        theses = repository.list_theses()
        inbox_counts = get_evidence_inbox_repository().status_counts()
        issuer_counts = get_evidence_inbox_repository().provider_status_counts("sec_edgar")
        return {
            "enabled": config.agent_tuning.vibe_investment_research_enabled,
            "shadow_mode": config.agent_tuning.vibe_investment_research_shadow_mode,
            "schema_version": SCHEMA_VERSION,
            "schema_components": {
                "research_core": SCHEMA_VERSION,
                "evidence_inbox": EVIDENCE_INBOX_SCHEMA_VERSION,
                "evidence_association": EVIDENCE_ASSOCIATION_SCHEMA_VERSION,
                "evidence_set_review": EVIDENCE_SET_REVIEW_SCHEMA_VERSION,
            },
            "thesis_count": len(theses),
            "evidence_inbox": {status.value: count for status, count in inbox_counts.items()},
            "issuer_disclosures": {
                "enabled": config.agent_tuning.vibe_investment_research_issuer_disclosures_enabled,
                "provider": "sec_edgar",
                "review_state": {status.value: count for status, count in issuer_counts.items()},
                "automatic_classification": False,
            },
            "macro_evidence": {
                "provider": "fred",
                "configured": FredMacroEvidenceProvider().configured,
                "automatic_collection": False,
                "automatic_classification": False,
                "historical_replay": "requires_alfred_vintage_data",
            },
            "positioning": "AI Investment Researcher",
            "output_contract": "Research Candidate, not a trade instruction",
        }

    @app.get("/investment-research/macro-evidence/status", dependencies=dependencies)
    async def investment_research_macro_evidence_status() -> dict[str, Any]:
        provider = FredMacroEvidenceProvider()
        return {
            "provider": provider.provider_name,
            "configured": provider.configured,
            "series": [
                {
                    "series_id": definition.series_id,
                    "title": definition.title,
                    "subject_id": definition.subject_id,
                }
                for definition in provider.series
            ],
            "collection_mode": "manual_only",
            "automatic_classification": False,
            "candidate_or_valuation_effect": "none_until_human_review",
            "historical_replay": "requires_alfred_vintage_data",
            "credentials_exposed": False,
        }

    @app.post("/investment-research/macro-evidence/collect", dependencies=dependencies)
    async def investment_research_macro_evidence_collect() -> dict[str, Any]:
        """Collect current FRED observations into the existing evidence inbox."""
        provider = FredMacroEvidenceProvider()
        now = datetime.now(timezone.utc)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    MacroEvidenceIngestionService(
                        get_evidence_inbox_repository()
                    ).ingest_fred,
                    provider,
                    as_of=date.today(),
                    ingested_at=now,
                ),
                timeout=30.0,
            )
        except TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail={
                    "provider": "fred",
                    "status": "timeout",
                    "evidence_ingested": 0,
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "provider": "fred",
                    "status": "collection_failed",
                    "error_type": type(exc).__name__,
                    "evidence_ingested": 0,
                },
            ) from exc
        return {
            **result.batch.to_dict(),
            "ingested": result.ingested,
            "deduplicated": result.deduplicated,
            "automatic_classification": False,
            "candidate_or_valuation_effect": "none_until_human_review",
            "scheduler_started": False,
            "notification_sent": False,
            "trading_executed": False,
        }

    @app.get("/investment-research/opportunity-daily/status", dependencies=dependencies)
    async def investment_research_opportunity_daily_status() -> dict[str, Any]:
        status = get_daily_opportunity_service().status()
        status["delivery"] = _delivery_status()
        status["automation"] = get_daily_opportunity_automation().status()
        status["shadow_portfolio"] = get_shadow_portfolio_tracker().status()
        status["vibe_research"] = get_vibe_research_coordinator().status()
        return status

    @app.get("/investment-research/opportunity-daily/latest", dependencies=dependencies)
    async def investment_research_opportunity_daily_latest() -> dict[str, Any]:
        report = get_daily_opportunity_service().latest()
        if report is None:
            raise HTTPException(status_code=404, detail="daily opportunity report not found")
        return {
            **report,
            "shadow_portfolio": get_shadow_portfolio_tracker().status(),
            "vibe_research": get_vibe_research_coordinator().status(),
        }

    @app.post("/investment-research/opportunity-daily/run", dependencies=dependencies)
    async def investment_research_opportunity_daily_run() -> dict[str, Any]:
        try:
            report = await asyncio.wait_for(
                asyncio.to_thread(get_daily_opportunity_service().run),
                timeout=90.0,
            )
            shadow = await asyncio.to_thread(
                get_shadow_portfolio_tracker().process,
                report,
            )
            return {**report, "shadow_portfolio": shadow}
        except TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail="daily opportunity data providers timed out; no sample data was used",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"daily opportunity report unavailable: {type(exc).__name__}",
            ) from exc

    @app.get(
        "/investment-research/thesis-initialization/watchlist",
        dependencies=dependencies,
    )
    async def investment_research_watchlist_thesis_initialization_status() -> dict[str, Any]:
        service = ManualThesisInitializationService(
            get_investment_research_repository(),
            get_evidence_association_repository(),
            get_evidence_set_review_repository(),
        )
        return {
            "items": service.status(),
            "human_review_required": True,
            "automatic_evidence_approval": False,
            "scheduler_started": False,
            "notification_sent": False,
            "trading_executed": False,
        }

    @app.post(
        "/investment-research/thesis-initialization/watchlist",
        dependencies=dependencies,
    )
    async def investment_research_watchlist_thesis_initialize(
        request: ManualThesisInitializationRequest,
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        command = ManualThesisInitializationCommand(
            thesis_id=request.thesis_id,
            core_claim=request.core_claim,
            confidence=request.confidence,
            supporting_evidence=tuple(
                ManualEvidenceDraft(
                    item.provider,
                    item.source_locator,
                    item.title,
                    item.summary,
                    item.published_at,
                )
                for item in request.supporting_evidence
            ),
            counter_evidence=tuple(
                ManualEvidenceDraft(
                    item.provider,
                    item.source_locator,
                    item.title,
                    item.summary,
                    item.published_at,
                )
                for item in request.counter_evidence
            ),
            catalysts=tuple(request.catalysts),
            kill_criteria=tuple(request.kill_criteria),
            next_review_at=now + timedelta(days=request.next_review_days),
            reviewer=request.reviewer,
            review_rationale=request.review_rationale,
            confirmed=request.confirm,
        )
        try:
            result = await asyncio.to_thread(
                ManualThesisInitializationService(
                    get_investment_research_repository(),
                    get_evidence_association_repository(),
                    get_evidence_set_review_repository(),
                ).initialize,
                command,
                initialized_at=now,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "review_rejected",
                    "reason": str(exc),
                    "thesis_id": request.thesis_id,
                },
            ) from exc
        return result.to_dict()

    @app.get("/investment-research/opportunity-daily/notification-preview", dependencies=dependencies)
    async def investment_research_opportunity_notification_preview() -> dict[str, Any]:
        report = get_daily_opportunity_service().latest()
        if report is None:
            raise HTTPException(status_code=404, detail="daily opportunity report not found")
        planner = OpportunityReportNotificationPlanner(get_operations_repository())
        planner.report_web_url = get_env_config().research_delivery.report_web_url
        return {**_delivery_status(), **planner.preview(report)}

    @app.post("/investment-research/opportunity-daily/notify", dependencies=dependencies)
    async def investment_research_opportunity_notify(
        request: OpportunityNotificationRequest,
    ) -> dict[str, Any]:
        if not request.confirm:
            raise HTTPException(status_code=422, detail="manual confirmation is required")
        report = get_daily_opportunity_service().latest()
        if report is None:
            raise HTTPException(status_code=404, detail="daily opportunity report not found")
        config = get_env_config().research_delivery
        if config.mode == "disabled":
            raise HTTPException(
                status_code=409,
                detail="research delivery is disabled; enable dry_run or live mode explicitly",
            )
        channels = tuple(dict.fromkeys(request.channels))
        transports = _delivery_transports(channels)
        missing = [channel.value for channel in channels if channel not in transports]
        if missing:
            raise HTTPException(
                status_code=409,
                detail=f"research delivery configuration is incomplete for: {', '.join(missing)}",
            )
        repository = get_operations_repository()
        planner = OpportunityReportNotificationPlanner(
            repository,
            report_web_url=config.report_web_url,
        )
        message_ids = planner.enqueue(report, channels, datetime.now(timezone.utc))
        delivered, failed = OutboxDispatcher(repository, transports).dispatch_message_ids(
            message_ids,
            datetime.now(timezone.utc),
        )
        return {
            "mode": config.mode,
            "channels": [channel.value for channel in channels],
            "delivered": delivered,
            "failed": failed,
            "duplicate_or_already_delivered": len(message_ids) - delivered - failed,
            "report_date": report["report_date"],
            "scheduler_started": False,
            "trading_executed": False,
        }

    @app.get("/investment-research/shadow-portfolio", dependencies=dependencies)
    async def investment_research_shadow_portfolio() -> dict[str, Any]:
        return get_shadow_portfolio_tracker().status()

    @app.post(
        "/investment-research/opportunity-daily/automation/run-once",
        dependencies=dependencies,
    )
    async def investment_research_daily_automation_run_once() -> dict[str, Any]:
        """Run one explicit read-only automation pass for operator verification."""
        return await _run_daily_opportunity_automation(datetime.now(timezone.utc))
    @app.get("/investment-research/theses", dependencies=dependencies)
    async def investment_research_theses(as_of: datetime | None = Query(default=None)) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        cutoff = _as_of(as_of)
        payloads: list[dict[str, Any]] = []
        for thesis in repository.list_theses():
            try:
                version = repository.current_version(thesis.thesis_id, cutoff)
            except KeyError:
                version = None
            payloads.append(_thesis_payload(thesis, version))
        return payloads

    @app.get("/investment-research/theses/{thesis_id}", dependencies=dependencies)
    async def investment_research_thesis(
        thesis_id: str,
        as_of: datetime | None = Query(default=None),
    ) -> dict[str, Any]:
        repository = get_investment_research_repository()
        try:
            thesis = repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        try:
            version = repository.current_version(thesis_id, _as_of(as_of))
        except KeyError:
            version = None
        return _thesis_payload(thesis, version)

    @app.get("/investment-research/theses/{thesis_id}/versions", dependencies=dependencies)
    async def investment_research_thesis_versions(thesis_id: str) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        return [_version_payload(version) for version in repository.list_thesis_versions(thesis_id)]

    @app.get("/investment-research/theses/{thesis_id}/initialization", dependencies=dependencies)
    async def investment_research_thesis_initialization(thesis_id: str) -> dict[str, Any]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        versions = repository.list_thesis_versions(thesis_id)
        if not versions:
            return {"thesis_id": thesis_id, "initialized": False, "research_state": "uninitialized"}
        first = versions[0]
        try:
            audit = repository.get_initialization_audit(first.thesis_version_id)
        except KeyError:
            return {
                "thesis_id": thesis_id,
                "initialized": True,
                "research_state": "legacy_version_without_initialization_audit",
                "thesis_version_id": first.thesis_version_id,
            }
        return {
            "thesis_id": thesis_id,
            "initialized": True,
            "research_state": "evidence_backed",
            "thesis_version_id": first.thesis_version_id,
            "initializer": audit.initializer,
            "approval_reference": audit.approval_reference,
            "evidence_set_review_id": audit.evidence_set_review_id,
            "initialized_at": audit.initialized_at.isoformat(),
        }

    @app.get("/investment-research/evidence-inbox", dependencies=dependencies)
    async def investment_research_evidence_inbox(
        status: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        try:
            status_filter = EvidenceInboxStatus(status) if status else None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown evidence inbox status") from exc
        rows = get_evidence_inbox_repository().list_items(status_filter, limit)
        return [
            {
                "inbox_item_id": row.item.inbox_item_id,
                "status": row.status.value,
                "provider": row.item.provider,
                "source_locator": row.item.source_locator,
                "title": row.item.title,
                "summary": row.item.summary,
                "published_at": row.item.published_at.isoformat(),
                "available_at": row.item.available_at.isoformat(),
                "observed_at": row.item.observed_at.isoformat(),
                "ingested_at": row.item.ingested_at.isoformat(),
                "quality_warnings": list(row.item.quality_warnings),
                "proposed_subject_type": row.item.proposed_subject_type.value,
                "proposed_subject_id": row.item.proposed_subject_id,
                "proposed_direction": row.item.proposed_direction.value,
                "review": None if row.review is None else {
                    "review_id": row.review.review_id,
                    "decision": row.review.decision.value,
                    "rationale": row.review.rationale,
                    "reviewer": row.review.reviewer,
                    "reviewed_at": row.review.reviewed_at.isoformat(),
                    "final_subject_type": (
                        row.review.final_subject_type.value if row.review.final_subject_type else None
                    ),
                    "final_subject_id": row.review.final_subject_id,
                    "final_direction": row.review.final_direction.value if row.review.final_direction else None,
                },
            }
            for row in rows
        ]

    @app.get("/investment-research/evidence-associations", dependencies=dependencies)
    async def investment_research_evidence_associations(
        subject_type: str = Query(...),
        subject_id: str = Query(..., min_length=1),
        as_of: datetime | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        try:
            resolved_type = EvidenceSubjectType(subject_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown evidence subject type") from exc
        associations = get_evidence_association_repository().list_for_subject(
            resolved_type, subject_id, _as_of(as_of)
        )
        return [
            {
                "association_id": association.association_id,
                "evidence_id": association.evidence_id,
                "subject_type": association.subject_type.value,
                "subject_id": association.subject_id,
                "direction": association.direction.value,
                "assessed_at": association.assessed_at.isoformat(),
                "assessor": association.assessor,
                "rationale": association.rationale,
                "supersedes_association_id": association.supersedes_association_id,
            }
            for association in associations
        ]

    @app.get("/investment-research/evidence-readiness", dependencies=dependencies)
    async def investment_research_evidence_readiness(
        as_of: datetime | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        cutoff = _as_of(as_of)
        service = ThesisEvidenceReadinessService(
            get_evidence_association_repository(), repository, get_evidence_set_review_repository()
        )
        payloads: list[dict[str, Any]] = []
        for thesis in repository.list_theses():
            try:
                repository.current_version(thesis.thesis_id, cutoff)
            except KeyError:
                payloads.append(_readiness_payload(service.assess(thesis.thesis_id, cutoff)))
        return payloads

    @app.get(
        "/investment-research/theses/{thesis_id}/evidence-readiness",
        dependencies=dependencies,
    )
    async def investment_research_thesis_evidence_readiness(
        thesis_id: str,
        as_of: datetime | None = Query(default=None),
    ) -> dict[str, Any]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        cutoff = _as_of(as_of)
        service = ThesisEvidenceReadinessService(
            get_evidence_association_repository(), repository, get_evidence_set_review_repository()
        )
        return _readiness_payload(service.assess(thesis_id, cutoff))

    @app.get(
        "/investment-research/theses/{thesis_id}/evidence-set-reviews",
        dependencies=dependencies,
    )
    async def investment_research_thesis_evidence_set_reviews(
        thesis_id: str,
        as_of: datetime | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        reviews = get_evidence_set_review_repository().list_for_thesis(
            thesis_id, _as_of(as_of)
        )
        return [
            {
                "review_id": review.review_id,
                "thesis_id": review.thesis_id,
                "association_ids": list(review.association_ids),
                "information_cutoff": review.information_cutoff.isoformat(),
                "decision": review.decision.value,
                "reviewer": review.reviewer,
                "rationale": review.rationale,
                "reviewed_at": review.reviewed_at.isoformat(),
                "strongest_counter_association_id": review.strongest_counter_association_id,
                "missing_evidence": list(review.missing_evidence),
                "quality_exception_rationale": review.quality_exception_rationale,
                "approval_reference": review.approval_reference,
            }
            for review in reviews
        ]

    @app.get("/investment-research/reviews", dependencies=dependencies)
    async def investment_research_reviews(as_of: datetime | None = Query(default=None)) -> list[dict[str, Any]]:
        reviews = get_investment_research_repository().due_reviews(_as_of(as_of))
        return [
            {
                "review_id": review.review_id,
                "thesis_id": review.thesis_id,
                "base_version_id": review.base_version_id,
                "scheduled_for": review.scheduled_for.isoformat(),
                "status": review.status.value,
            }
            for review in reviews
        ]

    @app.get("/investment-research/daily/{report_date}", dependencies=dependencies)
    async def investment_research_daily(report_date: date, mode: str = Query(default="shadow")) -> dict[str, Any]:
        try:
            return get_investment_research_repository().get_daily_thesis_report(report_date, mode).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="daily thesis report not found") from exc

    @app.get("/investment-research/daily-research/{report_date}", dependencies=dependencies)
    async def investment_research_full_daily(
        report_date: date, mode: str = Query(default="shadow")
    ) -> dict[str, Any]:
        try:
            return get_intelligence_repository().get_daily_research_report(report_date, mode).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="daily research report not found") from exc

    @app.get("/investment-research/discovery-leads", dependencies=dependencies)
    async def investment_research_discovery_leads(
        as_of: datetime | None = Query(default=None),
        disposition: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        try:
            disposition_filter = DiscoveryDisposition(disposition) if disposition else None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown discovery disposition") from exc
        leads = get_discovery_repository().list_leads(_as_of(as_of), disposition_filter)
        return [
            {
                "lead_id": lead.lead_id,
                "asset_id": lead.asset_id,
                "thesis_version_id": lead.thesis_version_id,
                "evidence_set_id": lead.evidence_set_id,
                "disposition": lead.disposition.value,
                "reasons": list(lead.reasons),
                "missing_evidence": list(lead.missing_evidence),
                "first_rejection_question": lead.first_rejection_question,
                "as_of": lead.as_of.isoformat(),
            }
            for lead in leads
        ]
