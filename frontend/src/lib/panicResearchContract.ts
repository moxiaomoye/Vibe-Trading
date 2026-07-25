export type PanicMarketRegime = "normal" | "correction" | "systemic_stress" | "panic" | "unknown";
export type PanicActionLevel = "watch" | "research" | "prepare" | "action_candidate";
export type PanicDateMode = "auto" | "selected";
export type PanicDateResolution =
  | "current_completed_trading_day"
  | "previous_completed_trading_day"
  | "selected_trading_day"
  | "selected_non_trading_day_adjusted"
  | "historical_data_unavailable"
  | "data_not_ready";
export type NotificationDecisionStatus =
  | "ineligible"
  | "duplicate"
  | "cooldown"
  | "awaiting_manual_confirmation"
  | "dry_run_ready";

export interface PanicResearchMarketContract {
  trade_date: string;
  regime: PanicMarketRegime;
  panic_observation: string;
  advance: number;
  decline: number;
  limit_down: number;
  median_daily_return: number | null;
}

export interface PanicResearchScreenedAssetContract {
  symbol: string;
  change_pct: number | null;
  relative_to_market: number | null;
  relative_to_sector: number | null;
  is_limit_down: boolean | null;
  data_gap: string | null;
}

export interface PanicResearchNotificationContract {
  status: NotificationDecisionStatus;
  eligible: boolean;
  reasons: string[];
  meaningful_state_change: boolean;
}

export interface PanicResearchCandidateContract {
  symbol: string;
  candidate_id: string | null;
  action_level: PanicActionLevel | null;
  confidence: number | null;
  quality_status: string;
  valuation_status: string;
  attribution_scope: string;
  scenario_value_range: [string, string] | null;
  supporting_evidence: string[];
  counter_evidence: string[];
  catalysts: string[];
  invalidation_conditions: string[];
  blocked_reasons: string[];
  data_gaps: string[];
  notification: PanicResearchNotificationContract | null;
}

export interface PanicResearchShadowReportContract {
  shadow_run: true;
  information_cutoff: string;
  requested_date: string | null;
  effective_trade_date: string;
  date_mode: PanicDateMode;
  date_resolution: PanicDateResolution;
  date_resolution_reason: string;
  source_date: string;
  availability_time: string;
  input_mode: string;
  data_source: string;
  market: PanicResearchMarketContract;
  screened_watchlist: PanicResearchScreenedAssetContract[];
  research_candidates: PanicResearchCandidateContract[];
  data_gaps: string[];
  versions: Record<string, string>;
  outcome_evaluation: {
    status: "pending" | "partially_evaluated" | "fully_evaluated";
    windows: Array<{
      horizon: number;
      status: "pending" | "evaluated";
      asset_return: number | null;
      benchmark_return: number | null;
      sector_return: number | null;
      maximum_drawdown: number | null;
      invalidation_triggered: boolean | null;
      data_gap: string | null;
    }>;
  };
  manual_review_required: true;
}

export interface CandidateDetailState {
  candidate: PanicResearchCandidateContract;
  evidence: {
    supporting: string[];
    counter: string[];
  };
  review: {
    catalysts: string[];
    invalidationConditions: string[];
    blockedReasons: string[];
    dataGaps: string[];
  };
}

export type PanicResearchErrorKind =
  | "authentication"
  | "not_found"
  | "unavailable"
  | "invalid_contract"
  | "data_not_ready"
  | "historical_data_unavailable"
  | "provider_unavailable"
  | "invalid_manual_import";

export type PanicResearchViewState =
  | { kind: "disabled"; reason: string }
  | { kind: "loading" }
  | {
      kind: "error";
      errorKind: PanicResearchErrorKind;
      message: string;
      reasons: string[];
    }
  | {
      kind: "ready";
      report: PanicResearchShadowReportContract;
      candidates: PanicResearchCandidateContract[];
      selected: CandidateDetailState | null;
      versions: Array<{ component: string; version: string }>;
    };

export class PanicResearchContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PanicResearchContractError";
  }
}

export const panicResearchLoading = (): PanicResearchViewState => ({ kind: "loading" });

export const panicResearchDisabled = (reason: string): PanicResearchViewState => ({
  kind: "disabled",
  reason,
});

export function panicResearchError(error: unknown): PanicResearchViewState {
  const status = statusFrom(error);
  const code = codeFrom(error);
  const errorKind: PanicResearchErrorKind = error instanceof PanicResearchContractError
    ? "invalid_contract"
    : status === 401 || status === 403
      ? "authentication"
      : code === "data_not_ready"
        ? "data_not_ready"
        : code === "historical_data_unavailable"
          ? "historical_data_unavailable"
          : code === "provider_unavailable"
            ? "provider_unavailable"
            : code === "invalid_manual_import"
              ? "invalid_manual_import"
              : status === 404
                ? "not_found"
                : "unavailable";
  return {
    kind: "error",
    errorKind,
    message: error instanceof Error ? error.message : "Panic research data is unavailable.",
    reasons: reasonsFrom(error),
  };
}

export function parsePanicResearchShadowReport(payload: unknown): PanicResearchShadowReportContract {
  const root = record(payload, "report");
  if (root.shadow_run !== true || root.manual_review_required !== true) {
    throw new PanicResearchContractError("Report must be an explicit manual-review shadow run.");
  }
  const market = parseMarket(root.market);
  const candidates = array(root.research_candidates, "research_candidates").map(parseCandidate);
  const watchlist = array(root.screened_watchlist, "screened_watchlist").map(parseScreenedAsset);
  const versionsRecord = record(root.versions, "versions");
  const versions = Object.fromEntries(
    Object.entries(versionsRecord).map(([key, value]) => [key, text(value, `versions.${key}`)]),
  );
  const informationCutoff = text(root.information_cutoff, "information_cutoff");
  const dateMode = root.date_mode === undefined
    ? "auto"
    : text(root.date_mode, "date_mode");
  if (!["auto", "selected"].includes(dateMode)) {
    throw new PanicResearchContractError(`Unknown date mode: ${dateMode}`);
  }
  const dateResolution = root.date_resolution === undefined
    ? "current_completed_trading_day"
    : text(root.date_resolution, "date_resolution");
  const dateResolutions = [
    "current_completed_trading_day",
    "previous_completed_trading_day",
    "selected_trading_day",
    "selected_non_trading_day_adjusted",
    "historical_data_unavailable",
    "data_not_ready",
  ];
  if (!dateResolutions.includes(dateResolution)) {
    throw new PanicResearchContractError(`Unknown date resolution: ${dateResolution}`);
  }
  return {
    shadow_run: true,
    information_cutoff: informationCutoff,
    requested_date: root.requested_date === undefined
      ? null
      : nullableText(root.requested_date, "requested_date"),
    effective_trade_date: root.effective_trade_date === undefined
      ? market.trade_date
      : text(root.effective_trade_date, "effective_trade_date"),
    date_mode: dateMode as PanicDateMode,
    date_resolution: dateResolution as PanicDateResolution,
    date_resolution_reason: root.date_resolution_reason === undefined
      ? "legacy report date context"
      : text(root.date_resolution_reason, "date_resolution_reason"),
    source_date: root.source_date === undefined
      ? market.trade_date
      : text(root.source_date, "source_date"),
    availability_time: root.availability_time === undefined
      ? informationCutoff
      : text(root.availability_time, "availability_time"),
    input_mode: root.input_mode === undefined
      ? "fixture"
      : text(root.input_mode, "input_mode"),
    data_source: root.data_source === undefined
      ? "unknown"
      : text(root.data_source, "data_source"),
    market,
    screened_watchlist: watchlist,
    research_candidates: candidates,
    data_gaps: stringArray(root.data_gaps, "data_gaps"),
    versions,
    outcome_evaluation: parseOutcomeEvaluation(root.outcome_evaluation),
    manual_review_required: true,
  };
}

function parseOutcomeEvaluation(
  value: unknown,
): PanicResearchShadowReportContract["outcome_evaluation"] {
  if (value === undefined) {
    return {
      status: "pending",
      windows: [5, 20, 60].map((horizon) => ({
        horizon,
        status: "pending",
        asset_return: null,
        benchmark_return: null,
        sector_return: null,
        maximum_drawdown: null,
        invalidation_triggered: null,
        data_gap: "outcome evaluation has not been loaded",
      })),
    };
  }
  const root = record(value, "outcome_evaluation");
  const status = text(root.status, "outcome_evaluation.status");
  if (!["pending", "partially_evaluated", "fully_evaluated"].includes(status)) {
    throw new PanicResearchContractError(`Unknown outcome status: ${status}`);
  }
  return {
    status: status as "pending" | "partially_evaluated" | "fully_evaluated",
    windows: array(root.windows, "outcome_evaluation.windows").map((raw, index) => {
      const item = record(raw, `outcome_evaluation.windows[${index}]`);
      const windowStatus = text(item.status, `outcome_evaluation.windows[${index}].status`);
      if (!["pending", "evaluated"].includes(windowStatus)) {
        throw new PanicResearchContractError(`Unknown outcome window status: ${windowStatus}`);
      }
      return {
        horizon: number(item.horizon, `outcome_evaluation.windows[${index}].horizon`),
        status: windowStatus as "pending" | "evaluated",
        asset_return: nullableNumber(item.asset_return, "asset_return"),
        benchmark_return: nullableNumber(item.benchmark_return, "benchmark_return"),
        sector_return: nullableNumber(item.sector_return, "sector_return"),
        maximum_drawdown: nullableNumber(item.maximum_drawdown, "maximum_drawdown"),
        invalidation_triggered: nullableBoolean(item.invalidation_triggered, "invalidation_triggered"),
        data_gap: nullableText(item.data_gap, "data_gap"),
      };
    }),
  };
}

export function panicResearchReady(
  payload: unknown,
  selectedCandidateId: string | null = null,
): PanicResearchViewState {
  const report = parsePanicResearchShadowReport(payload);
  const selectedCandidate = selectedCandidateId
    ? report.research_candidates.find((candidate) => candidate.candidate_id === selectedCandidateId) ?? null
    : null;
  return {
    kind: "ready",
    report,
    candidates: report.research_candidates,
    selected: selectedCandidate ? candidateDetail(selectedCandidate) : null,
    versions: Object.entries(report.versions)
      .map(([component, version]) => ({ component, version }))
      .sort((left, right) => left.component.localeCompare(right.component)),
  };
}

export function selectPanicResearchCandidate(
  state: PanicResearchViewState,
  candidateId: string | null,
): PanicResearchViewState {
  if (state.kind !== "ready") return state;
  const selected = candidateId
    ? state.candidates.find((candidate) => candidate.candidate_id === candidateId) ?? null
    : null;
  return { ...state, selected: selected ? candidateDetail(selected) : null };
}

function candidateDetail(candidate: PanicResearchCandidateContract): CandidateDetailState {
  return {
    candidate,
    evidence: {
      supporting: candidate.supporting_evidence,
      counter: candidate.counter_evidence,
    },
    review: {
      catalysts: candidate.catalysts,
      invalidationConditions: candidate.invalidation_conditions,
      blockedReasons: candidate.blocked_reasons,
      dataGaps: candidate.data_gaps,
    },
  };
}

function parseMarket(value: unknown): PanicResearchMarketContract {
  const item = record(value, "market");
  const regime = text(item.regime, "market.regime");
  if (!["normal", "correction", "systemic_stress", "panic", "unknown"].includes(regime)) {
    throw new PanicResearchContractError(`Unknown market regime: ${regime}`);
  }
  return {
    trade_date: text(item.trade_date, "market.trade_date"),
    regime: regime as PanicMarketRegime,
    panic_observation: text(item.panic_observation, "market.panic_observation"),
    advance: number(item.advance, "market.advance"),
    decline: number(item.decline, "market.decline"),
    limit_down: number(item.limit_down, "market.limit_down"),
    median_daily_return: nullableNumber(item.median_daily_return, "market.median_daily_return"),
  };
}

function parseScreenedAsset(value: unknown): PanicResearchScreenedAssetContract {
  const item = record(value, "screened asset");
  return {
    symbol: text(item.symbol, "screened asset.symbol"),
    change_pct: nullableNumber(item.change_pct, "screened asset.change_pct"),
    relative_to_market: nullableNumber(item.relative_to_market, "screened asset.relative_to_market"),
    relative_to_sector: nullableNumber(item.relative_to_sector, "screened asset.relative_to_sector"),
    is_limit_down: nullableBoolean(item.is_limit_down, "screened asset.is_limit_down"),
    data_gap: nullableText(item.data_gap, "screened asset.data_gap"),
  };
}

function parseCandidate(value: unknown): PanicResearchCandidateContract {
  const item = record(value, "research candidate");
  const actionLevel = nullableText(item.action_level, "research candidate.action_level");
  if (actionLevel !== null && !["watch", "research", "prepare", "action_candidate"].includes(actionLevel)) {
    throw new PanicResearchContractError(`Unknown action level: ${actionLevel}`);
  }
  return {
    symbol: text(item.symbol, "research candidate.symbol"),
    candidate_id: nullableText(item.candidate_id, "research candidate.candidate_id"),
    action_level: actionLevel as PanicActionLevel | null,
    confidence: nullableNumber(item.confidence, "research candidate.confidence"),
    quality_status: text(item.quality_status, "research candidate.quality_status"),
    valuation_status: text(item.valuation_status, "research candidate.valuation_status"),
    attribution_scope: text(item.attribution_scope, "research candidate.attribution_scope"),
    scenario_value_range: pairOrNull(item.scenario_value_range),
    supporting_evidence: stringArray(item.supporting_evidence, "supporting_evidence"),
    counter_evidence: stringArray(item.counter_evidence, "counter_evidence"),
    catalysts: stringArray(item.catalysts, "catalysts"),
    invalidation_conditions: stringArray(item.invalidation_conditions, "invalidation_conditions"),
    blocked_reasons: stringArray(item.blocked_reasons, "blocked_reasons"),
    data_gaps: stringArray(item.data_gaps, "candidate.data_gaps"),
    notification: item.notification === null ? null : parseNotification(item.notification),
  };
}

function parseNotification(value: unknown): PanicResearchNotificationContract {
  const item = record(value, "notification");
  const status = text(item.status, "notification.status");
  const statuses = ["ineligible", "duplicate", "cooldown", "awaiting_manual_confirmation", "dry_run_ready"];
  if (!statuses.includes(status)) throw new PanicResearchContractError(`Unknown notification status: ${status}`);
  return {
    status: status as NotificationDecisionStatus,
    eligible: boolean(item.eligible, "notification.eligible"),
    reasons: stringArray(item.reasons, "notification.reasons"),
    meaningful_state_change: boolean(item.meaningful_state_change, "notification.meaningful_state_change"),
  };
}

function statusFrom(error: unknown): number | undefined {
  if (!error || typeof error !== "object" || !("status" in error)) return undefined;
  return typeof error.status === "number" ? error.status : undefined;
}

function codeFrom(error: unknown): string | undefined {
  if (!error || typeof error !== "object" || !("code" in error)) return undefined;
  return typeof error.code === "string" ? error.code : undefined;
}

function reasonsFrom(error: unknown): string[] {
  if (!error || typeof error !== "object" || !("reasons" in error)) return [];
  return Array.isArray(error.reasons)
    ? error.reasons.filter((item): item is string => typeof item === "string")
    : [];
}

function record(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new PanicResearchContractError(`${field} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new PanicResearchContractError(`${field} must be an array.`);
  return value;
}

function text(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new PanicResearchContractError(`${field} must be a non-empty string.`);
  }
  return value;
}

function nullableText(value: unknown, field: string): string | null {
  return value === null ? null : text(value, field);
}

function number(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new PanicResearchContractError(`${field} must be a finite number.`);
  }
  return value;
}

function nullableNumber(value: unknown, field: string): number | null {
  return value === null ? null : number(value, field);
}

function boolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") throw new PanicResearchContractError(`${field} must be a boolean.`);
  return value;
}

function nullableBoolean(value: unknown, field: string): boolean | null {
  return value === null ? null : boolean(value, field);
}

function stringArray(value: unknown, field: string): string[] {
  return array(value, field).map((item, index) => text(item, `${field}[${index}]`));
}

function pairOrNull(value: unknown): [string, string] | null {
  if (value === null) return null;
  const values = array(value, "scenario_value_range");
  if (values.length !== 2) throw new PanicResearchContractError("scenario_value_range must contain two values.");
  return [text(values[0], "scenario_value_range[0]"), text(values[1], "scenario_value_range[1]")];
}
