import {
  PanicResearchContractError,
  panicResearchDisabled,
  panicResearchError,
  panicResearchLoading,
  panicResearchReady,
  parsePanicResearchShadowReport,
  selectPanicResearchCandidate,
} from "../panicResearchContract";


function report() {
  return {
    shadow_run: true,
    information_cutoff: "2026-07-22T10:31:00+00:00",
    market: {
      trade_date: "2026-07-22",
      regime: "panic",
      panic_observation: "extreme_panic",
      advance: 6,
      decline: 114,
      limit_down: 120,
      median_daily_return: -0.06,
    },
    screened_watchlist: [{
      symbol: "600522.SH", change_pct: -0.06, relative_to_market: -0.01,
      relative_to_sector: null, is_limit_down: false, data_gap: "sector unavailable",
    }],
    research_candidates: [{
      symbol: "600522.SH",
      candidate_id: "candidate-1",
      action_level: "action_candidate",
      confidence: 0.9,
      quality_status: "configured",
      valuation_status: "configured",
      attribution_scope: "market_systemic",
      scenario_value_range: ["63.175", "203.125"],
      supporting_evidence: ["support"],
      counter_evidence: ["counter"],
      catalysts: ["demand stabilization"],
      invalidation_conditions: ["structural impairment"],
      blocked_reasons: [],
      data_gaps: ["sector unavailable"],
      notification: {
        status: "awaiting_manual_confirmation",
        eligible: true,
        reasons: ["manual_confirmation_required"],
        meaningful_state_change: false,
      },
    }],
    data_gaps: ["sector unavailable"],
    versions: { notification_decision: "1.0.0", panic_rule: "1.0.0" },
    manual_review_required: true,
  };
}


describe("panic research frontend contract", () => {
  it("maps a backend shadow report without recalculating business rules", () => {
    const state = panicResearchReady(report(), "candidate-1");
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") throw new Error("expected ready state");
    expect(state.candidates[0].action_level).toBe("action_candidate");
    expect(state.selected?.evidence).toEqual({ supporting: ["support"], counter: ["counter"] });
    expect(state.selected?.review.invalidationConditions).toEqual(["structural impairment"]);
    expect(state.versions).toEqual([
      { component: "notification_decision", version: "1.0.0" },
      { component: "panic_rule", version: "1.0.0" },
    ]);
  });

  it("supports loading, disabled and candidate-detail selection states", () => {
    expect(panicResearchLoading()).toEqual({ kind: "loading" });
    expect(panicResearchDisabled("feature disabled")).toEqual({ kind: "disabled", reason: "feature disabled" });
    const ready = panicResearchReady(report());
    const selected = selectPanicResearchCandidate(ready, "candidate-1");
    expect(selected.kind === "ready" && selected.selected?.candidate.candidate_id).toBe("candidate-1");
    const cleared = selectPanicResearchCandidate(selected, null);
    expect(cleared.kind === "ready" && cleared.selected).toBeNull();
  });

  it("maps transport and contract errors into explicit error states", () => {
    expect(panicResearchError(Object.assign(new Error("key required"), { status: 401 }))).toMatchObject({
      kind: "error", errorKind: "authentication",
    });
    expect(panicResearchError(Object.assign(new Error("missing"), { status: 404 }))).toMatchObject({
      kind: "error", errorKind: "not_found",
    });
    expect(panicResearchError(new PanicResearchContractError("bad shape"))).toMatchObject({
      kind: "error", errorKind: "invalid_contract",
    });
  });

  it("rejects non-shadow, unknown state and malformed evidence shapes", () => {
    expect(() => parsePanicResearchShadowReport({ ...report(), shadow_run: false })).toThrow(/shadow run/);
    expect(() => parsePanicResearchShadowReport({
      ...report(), market: { ...report().market, regime: "bullish" },
    })).toThrow(/Unknown market regime/);
    const malformed = report();
    malformed.research_candidates[0].supporting_evidence = "support" as unknown as string[];
    expect(() => parsePanicResearchShadowReport(malformed)).toThrow(/supporting_evidence must be an array/);
  });
});
