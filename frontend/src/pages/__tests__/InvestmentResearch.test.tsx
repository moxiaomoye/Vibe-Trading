import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { InvestmentResearchStatus, InvestmentResearchThesis } from "@/lib/api";
import { InvestmentResearch } from "../InvestmentResearch";


const apiMock = vi.hoisted(() => ({
  getInvestmentResearchStatus: vi.fn(),
  getDailyOpportunityStatus: vi.fn(),
  getLatestDailyOpportunityReport: vi.fn(),
  runDailyOpportunityReport: vi.fn(),
  getDailyOpportunityNotificationPreview: vi.fn(),
  notifyDailyOpportunityReport: vi.fn(),
  listInvestmentResearchTheses: vi.fn(),
  getWatchlistThesisInitialization: vi.fn(),
  initializeWatchlistThesis: vi.fn(),
  listInvestmentResearchEvidenceInbox: vi.fn(),
  listInvestmentResearchEvidenceReadiness: vi.fn(),
  getInvestmentResearchDaily: vi.fn(),
  getPanicShadowStatus: vi.fn(),
  getLatestPanicShadowReport: vi.fn(),
  runCurrentPanicShadowReport: vi.fn(),
  runManualPanicShadowReport: vi.fn(),
  runPanicShadowReport: vi.fn(),
  evaluateAutomaticHistoricalPrices: vi.fn(),
  evaluateManualHistoricalPrices: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
  isDisabledFeatureError: () => false,
}));

const status: InvestmentResearchStatus = {
  enabled: false,
  shadow_mode: true,
  schema_version: 9,
  schema_components: {
    research_core: 3,
    evidence_inbox: 9,
    evidence_association: 10,
    evidence_set_review: 11,
  },
  thesis_count: 1,
  evidence_inbox: { pending: 0, accepted: 0, rejected: 0 },
  positioning: "AI Investment Researcher",
  output_contract: "Research Candidate, not a trade instruction",
};

const theses: InvestmentResearchThesis[] = [{
  thesis_id: "ai-industry",
  name: "AI Industry",
  parent_thesis_id: null,
  scope: "theme",
  created_at: "2026-07-21T00:00:00Z",
  current_version: null,
  research_state: "uninitialized",
}];

describe("InvestmentResearch page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getInvestmentResearchStatus.mockResolvedValue(status);
    apiMock.getDailyOpportunityStatus.mockResolvedValue({
      enabled: true,
      read_only: true,
      watchlist: [
        { symbol: "600522.SH", name: "中天科技", asset_type: "stock" },
        { symbol: "588000.SH", name: "科创50ETF", asset_type: "etf" },
      ],
      rules: {
        lookback_trading_days: 60,
        asset_return_pct_lte: -30,
        shanghai_point_change_lte: -200,
        limit_down_count_gte: 1000,
        match: "any",
      },
      notifications: false,
      scheduler: false,
      trading: false,
    });
    apiMock.getLatestDailyOpportunityReport.mockRejectedValue(
      Object.assign(new Error("not found"), { status: 404 }),
    );
    apiMock.listInvestmentResearchTheses.mockResolvedValue(theses);
    apiMock.getWatchlistThesisInitialization.mockResolvedValue({
      items: [{
        thesis_id: "thesis:600522.SH",
        symbol: "600522.SH",
        name: "中天科技长期价值逻辑",
        scope: "company",
        initialized: false,
        thesis_version_id: null,
        proposed_core_claim: "中天科技核心业务仍有长期竞争力。",
        proposed_catalysts: ["高毛利业务改善"],
        proposed_kill_criteria: ["现金流结构性恶化"],
      }, {
        thesis_id: "thesis:588000.SH",
        symbol: "588000.SH",
        name: "科创50ETF长期价值逻辑",
        scope: "theme",
        initialized: false,
        thesis_version_id: null,
        proposed_core_claim: "科创50长期产业逻辑仍然成立。",
        proposed_catalysts: ["核心成分盈利改善"],
        proposed_kill_criteria: ["产业逻辑广泛下修"],
      }],
      human_review_required: true,
      automatic_evidence_approval: false,
      scheduler_started: false,
      notification_sent: false,
      trading_executed: false,
    });
    apiMock.initializeWatchlistThesis.mockResolvedValue({
      thesis_id: "thesis:600522.SH",
      thesis_version_id: "version-1",
      initialized: true,
      created: true,
      evidence_count: 2,
      next_review_at: "2026-08-30T12:00:00Z",
      scheduler_started: false,
      notification_sent: false,
      trading_executed: false,
    });
    apiMock.listInvestmentResearchEvidenceInbox.mockResolvedValue([]);
    apiMock.listInvestmentResearchEvidenceReadiness.mockResolvedValue([{
      thesis_id: "ai-industry",
      as_of: "2026-07-21T10:00:00Z",
      verdict: "needs_counter",
      supporting_association_ids: ["association-1"],
      counter_association_ids: [],
      neutral_association_ids: [],
      blocking_gaps: ["No current counter evidence is available."],
      quality_warnings: [],
      first_rejection_question: "What is the strongest evidence that could make this Thesis wrong?",
      approval_review_id: null,
    }]);
    apiMock.getInvestmentResearchDaily.mockRejectedValue(new Error("not generated"));
    apiMock.getPanicShadowStatus.mockResolvedValue({
      enabled: true,
      mode: "shadow",
      read_only: true,
      explicit_input_only: false,
      explicit_input_supported: true,
      provider_run_supported: true,
      persistent: true,
      persistence_scope: "successful_provider_runs_only",
      scheduler_enabled: false,
      notification_enabled: false,
      trading_enabled: false,
      manual_review_required: true,
      date_context: {
        date_mode: "auto",
        requested_date: null,
        effective_trade_date: "2026-07-24",
        date_resolution: "previous_completed_trading_day",
        information_cutoff: "2026-07-24T18:30:00+08:00",
        date_resolution_reason: "latest completed trading day",
      },
    });
    apiMock.getLatestPanicShadowReport.mockRejectedValue({ status: 404 });
  });

  it("shows evidence initialization without inventing confidence", async () => {
    render(<InvestmentResearch />);
    expect(await screen.findByText("AI Investment Researcher")).toBeInTheDocument();
    expect(screen.getByText("AI Industry")).toBeInTheDocument();
    expect(screen.getByText("证据就绪度：缺少反方证据")).toBeInTheDocument();
    expect(screen.getByText(/What is the strongest evidence/)).toBeInTheDocument();
    expect(screen.getByText("等待证据初始化")).toBeInTheDocument();
    expect(screen.getByText(/未初始化节点不显示 Confidence/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "生成最近交易日盘后报告" })).toBeInTheDocument();
  });

  it("shows a truthful empty daily state and read-only boundary", async () => {
    render(<InvestmentResearch />);
    expect(await screen.findByText(/今日完整日报尚未生成/)).toBeInTheDocument();
    expect(screen.getByText(/V2 自动研究当前关闭/)).toBeInTheDocument();
    expect(screen.getByText("Research Candidate，不是交易指令")).toBeInTheDocument();
    expect(screen.getByText("当前没有待审证据。")).toBeInTheDocument();
    expect(screen.getByText("当前没有已接受证据。")).toBeInTheDocument();
  });

  it("submits an explicit balanced Thesis review for the focused watchlist", async () => {
    render(<InvestmentResearch />);

    const initializeButtons = await screen.findAllByRole("button", {
      name: "审核证据并建立 Version 1",
    });
    fireEvent.click(initializeButtons[0]);
    const locators = screen.getAllByLabelText("原文URL或来源定位");
    const titles = screen.getAllByLabelText("证据标题");
    const summaries = screen.getAllByLabelText("证据摘要");
    fireEvent.change(locators[0], { target: { value: "https://example.test/support" } });
    fireEvent.change(locators[1], { target: { value: "https://example.test/counter" } });
    fireEvent.change(titles[0], { target: { value: "支持证据标题" } });
    fireEvent.change(titles[1], { target: { value: "反方证据标题" } });
    fireEvent.change(summaries[0], { target: { value: "经过人工核验的支持事实。" } });
    fireEvent.change(summaries[1], { target: { value: "经过人工核验的反方事实。" } });
    fireEvent.change(screen.getByLabelText("审核理由"), {
      target: { value: "我核对了来源，并确认最强反方证据没有使逻辑失效。" },
    });
    fireEvent.click(screen.getByLabelText(/我已阅读来源/));
    fireEvent.click(screen.getByRole("button", {
      name: "确认审核并建立 Version 1",
    }));

    await waitFor(() => expect(apiMock.initializeWatchlistThesis).toHaveBeenCalled());
    const payload = apiMock.initializeWatchlistThesis.mock.calls[0][0];
    expect(payload.thesis_id).toBe("thesis:600522.SH");
    expect(payload.supporting_evidence).toHaveLength(1);
    expect(payload.counter_evidence).toHaveLength(1);
    expect(payload.confirm).toBe(true);
    expect(await screen.findByText(/审核版本已建立/)).toBeInTheDocument();
  });

  it("generates and renders the unified two-asset daily report", async () => {
    apiMock.runDailyOpportunityReport.mockResolvedValue({
      report_version: "1.0",
      report_date: "2026-07-29",
      generated_at: "2026-07-29T10:00:00Z",
      read_only: true,
      shadow_run: true,
      market: {
        panic: true,
        panic_triggers: [{
          code: "MARKET_DRAWDOWN",
          label: "上证指数60个交易日下跌超过200点",
          observed: -220,
          threshold: -200,
        }],
        shanghai_symbol: "000001.SH",
        shanghai_effective_trade_date: "2026-07-29",
        shanghai_close: 3200,
        shanghai_60d_point_change: -220,
        limit_down_count: 100,
        limit_down_count_quality: "approximate_or_cached",
        market_context_source: "fixture",
      },
      assets: [{
        symbol: "600522.SH",
        name: "中天科技",
        asset_type: "stock",
        effective_trade_date: "2026-07-29",
        latest_close: 18.5,
        return_60d_pct: -32.5,
        panic: true,
        panic_triggers: [
          { code: "ASSET_PANIC", label: "中天科技60个交易日跌幅超过30%", observed: -32.5, threshold: -30 },
          { code: "MARKET_DRAWDOWN", label: "上证指数60个交易日下跌超过200点", observed: -220, threshold: -200 },
        ],
        action_level: "prepare",
        action_label: "准备研究与资金",
        supporting_evidence: ["中天科技60个交易日跌幅超过30%"],
        counter_evidence: [],
        next_condition: "三项条件同时触发后进入分批建仓观察区",
        data_source: "vibe_market_loader_auto",
        data_quality: "provider_chain_unverified",
      }, {
        symbol: "588000.SH",
        name: "科创50ETF",
        asset_type: "etf",
        effective_trade_date: "2026-07-29",
        latest_close: 0.9,
        return_60d_pct: -10,
        panic: true,
        panic_triggers: [{
          code: "MARKET_DRAWDOWN",
          label: "上证指数60个交易日下跌超过200点",
          observed: -220,
          threshold: -200,
        }],
        action_level: "research",
        action_label: "恐慌观察",
        supporting_evidence: ["上证指数60个交易日下跌超过200点"],
        counter_evidence: ["标的60日跌幅为-10.00%，尚未达到30%"],
        next_condition: "再触发一项恐慌条件后升级为准备阶段",
        data_source: "vibe_market_loader_auto",
        data_quality: "provider_chain_unverified",
      }],
      data_sources: { prices: "Vibe market loader auto fallback chain", market_context: "fixture" },
      data_gaps: [],
      unresolved_symbols: [],
      conclusion: "当前最值得研究的是中天科技：准备研究与资金。",
      notifications_sent: false,
      scheduler_started: false,
      trading_executed: false,
    });

    render(<InvestmentResearch />);
    fireEvent.click(await screen.findByRole("button", { name: "生成今日研究日报" }));

    expect(await screen.findByText("当前最值得研究的是中天科技：准备研究与资金。")).toBeInTheDocument();
    expect(screen.getAllByText("准备研究与资金").length).toBeGreaterThan(0);
    expect(screen.getByText("恐慌观察")).toBeInTheDocument();
    expect(screen.getByText(/-220\.00 点/)).toBeInTheDocument();
  });

  it("does not crash when optional routes return disabled JSON stubs", async () => {
    const disabled = {
      enabled: false,
      status: "disabled",
      reason: "feature_not_enabled",
    };
    apiMock.getInvestmentResearchStatus.mockResolvedValue(disabled);
    apiMock.listInvestmentResearchTheses.mockResolvedValue(disabled);
    apiMock.listInvestmentResearchEvidenceInbox.mockResolvedValue(disabled);
    apiMock.listInvestmentResearchEvidenceReadiness.mockResolvedValue(disabled);

    render(<InvestmentResearch />);

    expect(await screen.findByText(/V2 自动研究当前关闭/)).toBeInTheDocument();
    expect(screen.getByText("AI Investment Researcher")).toBeInTheDocument();
    expect(screen.queryByText(/filter is not a function/)).not.toBeInTheDocument();
  });

  it("generates and renders the current post-close shadow report", async () => {
    apiMock.runCurrentPanicShadowReport.mockResolvedValue({
      shadow_run: true,
      information_cutoff: "2026-07-24T10:30:00+00:00",
      market: {
        trade_date: "2026-07-24",
        regime: "panic",
        panic_observation: "panic",
        advance: 420,
        decline: 4300,
        limit_down: 160,
        median_daily_return: -0.047,
      },
      screened_watchlist: [],
      research_candidates: [],
      data_gaps: ["sector returns unavailable"],
      versions: { panic_rule: "1.0.0", candidate_pipeline: "not_run" },
      manual_review_required: true,
    });
    render(<InvestmentResearch />);

    fireEvent.click(await screen.findByRole("button", { name: "生成最近交易日盘后报告" }));

    await waitFor(() => expect(apiMock.runCurrentPanicShadowReport).toHaveBeenCalledWith({
      date_mode: "auto",
      requested_date: null,
    }));
    expect((await screen.findAllByText("panic")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("420/4300/160")).toBeInTheDocument();
    expect(screen.getByText("sector returns unavailable")).toBeInTheDocument();
  });

  it("imports an explicit manual JSON manifest through the browser", async () => {
    apiMock.runManualPanicShadowReport.mockResolvedValue({
      shadow_run: true,
      information_cutoff: "2026-07-24T10:30:00+00:00",
      market: {
        trade_date: "2026-07-24",
        regime: "correction",
        panic_observation: "caution",
        advance: 900,
        decline: 3600,
        limit_down: 40,
        median_daily_return: -0.025,
      },
      screened_watchlist: [],
      research_candidates: [],
      data_gaps: ["market breadth reflects the imported universe only"],
      versions: { panic_rule: "1.0.0", candidate_pipeline: "not_run" },
      manual_review_required: true,
    });
    const manifest = {
      schema_version: "1.0",
      source: "manual_import",
      source_date: "2026-07-24",
      availability_time: "2026-07-24T18:30:00+08:00",
      rows: [],
    };
    render(<InvestmentResearch />);

    fireEvent.change(await screen.findByLabelText("导入对应日期 JSON"), {
      target: {
        files: [
          new File([JSON.stringify(manifest)], "post-close.json", {
            type: "application/json",
          }),
        ],
      },
    });

    await waitFor(() => {
      expect(apiMock.runManualPanicShadowReport).toHaveBeenCalledWith(
        manifest,
        { date_mode: "auto", requested_date: null },
      );
    });
    expect(await screen.findByText("correction")).toBeInTheDocument();
    expect(screen.getByText(/imported universe only/)).toBeInTheDocument();
  });

  it("imports historical prices and displays the T+20 outcome", async () => {
    apiMock.evaluateManualHistoricalPrices.mockResolvedValue({
      evaluation_date: "2025-07-21",
      stock_code: "000001",
      benchmark_code: "000300",
      entry_price: 10,
      data_source: "synthetic_hand_calculable_sample",
      input_mode: "sample",
      adjustment: "qfq",
      capability: "sample_contract",
      coverage: {
        first_trade_date: "2025-07-21",
        last_trade_date: "2025-08-18",
        row_count: 21,
      },
      warnings: ["sample data is synthetic and does not validate investment performance"],
      horizons: [{
        horizon: 20,
        target_trading_date: "2025-08-18",
        asset_return: 0.2,
        benchmark_return: 0.025,
        excess_return: 0.175,
        maximum_drawdown: -0.3076923077,
        data_gap: null,
        calculation_status: "complete",
      }],
    });
    const manifest = {
      schema_version: "1.0",
      input_mode: "sample",
      data_source: "synthetic_hand_calculable_sample",
      prices: [],
    };
    render(<InvestmentResearch />);

    fireEvent.change(await screen.findByLabelText("导入历史价格 JSON"), {
      target: {
        files: [
          new File([JSON.stringify(manifest)], "historical-prices.json", {
            type: "application/json",
          }),
        ],
      },
    });

    await waitFor(() => {
      expect(apiMock.evaluateManualHistoricalPrices).toHaveBeenCalledWith(manifest);
    });
    expect(await screen.findByText("2025-08-18")).toBeInTheDocument();
    expect(screen.getByText("20.00%")).toBeInTheDocument();
    expect(screen.getByText("2.50% / 17.50%")).toBeInTheDocument();
  });

  it("uses automatic historical acquisition as the default T+20 flow", async () => {
    apiMock.evaluateAutomaticHistoricalPrices.mockResolvedValue({
      evaluation_date: "2025-07-21",
      stock_code: "000001",
      benchmark_code: "000300",
      entry_price: 10,
      data_source: "component_providers",
      input_mode: "provider",
      adjustment: "qfq",
      capability: "provider",
      component_sources: {
        stock: "tencent",
        benchmark: "tushare",
      },
      provider_attempts: [],
      verification_status: "provider_acquired_unverified",
      coverage: {
        first_trade_date: "2025-07-21",
        last_trade_date: "2025-08-18",
        row_count: 21,
      },
      warnings: [],
      horizons: [{
        horizon: 20,
        target_trading_date: "2025-08-18",
        asset_return: 0.2,
        benchmark_return: 0.025,
        excess_return: 0.175,
        maximum_drawdown: -0.1,
        data_gap: null,
        calculation_status: "complete",
      }],
    });
    render(<InvestmentResearch />);

    fireEvent.change(await screen.findByLabelText("历史评估日期"), {
      target: { value: "2025-07-21" },
    });
    fireEvent.click(screen.getByRole("button", { name: "自动获取并评测 T+20" }));

    await waitFor(() => {
      expect(apiMock.evaluateAutomaticHistoricalPrices).toHaveBeenCalledWith({
        stock_code: "000001",
        evaluation_date: "2025-07-21",
        horizon: 20,
      });
    });
    expect(await screen.findByText("stock: tencent；benchmark: tushare")).toBeInTheDocument();
    expect(screen.getByText(/provider_acquired_unverified/)).toBeInTheDocument();
    expect(screen.getByText("自动获取失败 / 高级选项：手工 JSON 导入")).toBeInTheDocument();
  });

  it("does not submit an evaluation date that cannot have reached T+20", async () => {
    render(<InvestmentResearch />);

    const input = await screen.findByLabelText("历史评估日期");
    fireEvent.change(input, {
      target: { value: new Date().toISOString().slice(0, 10) },
    });

    expect(screen.getByRole("button", { name: "自动获取并评测 T+20" })).toBeDisabled();
    expect(apiMock.evaluateAutomaticHistoricalPrices).not.toHaveBeenCalled();
  });

  it("runs a selected historical date and displays resolved provenance", async () => {
    apiMock.runCurrentPanicShadowReport.mockResolvedValue({
      shadow_run: true,
      information_cutoff: "2026-07-23T10:30:00+00:00",
      requested_date: "2026-07-23",
      effective_trade_date: "2026-07-23",
      date_mode: "selected",
      date_resolution: "selected_trading_day",
      date_resolution_reason: "the selected date is a completed trading day",
      source_date: "2026-07-23",
      availability_time: "2026-07-23T10:30:00+00:00",
      input_mode: "archive",
      data_source: "manual_import",
      market: {
        trade_date: "2026-07-23", regime: "normal", panic_observation: "normal",
        advance: 2000, decline: 1800, limit_down: 3, median_daily_return: 0.001,
      },
      screened_watchlist: [], research_candidates: [], data_gaps: [],
      versions: { panic_rule: "1.0.0" },
      outcome_evaluation: {
        status: "pending",
        windows: [5, 20, 60].map((horizon) => ({
          horizon, status: "pending", asset_return: null, benchmark_return: null,
          sector_return: null, maximum_drawdown: null,
          invalidation_triggered: null, data_gap: "pending",
        })),
      },
      manual_review_required: true,
    });
    render(<InvestmentResearch />);

    fireEvent.change(await screen.findByLabelText("日期模式"), {
      target: { value: "selected" },
    });
    fireEvent.change(screen.getByLabelText("分析日期"), {
      target: { value: "2026-07-23" },
    });
    fireEvent.click(screen.getByRole("button", { name: "回放所选日期" }));

    await waitFor(() => expect(apiMock.runCurrentPanicShadowReport).toHaveBeenCalledWith({
      date_mode: "selected",
      requested_date: "2026-07-23",
    }));
    expect(await screen.findByText("archive / manual_import")).toBeInTheDocument();
    expect(screen.getByText("selected_trading_day")).toBeInTheDocument();
    expect(screen.getByText("5日：pending")).toBeInTheDocument();
  });

  it("keeps Manual Import available and shows structured provider reasons", async () => {
    apiMock.runCurrentPanicShadowReport.mockRejectedValue(Object.assign(
      new Error("all current spot sources are unavailable"),
      {
        status: 503,
        code: "provider_unavailable",
        reasons: ["spot upstream request failed"],
      },
    ));
    render(<InvestmentResearch />);

    fireEvent.click(await screen.findByRole("button", { name: "生成最近交易日盘后报告" }));

    expect(await screen.findByText(/all current spot sources are unavailable/)).toBeInTheDocument();
    expect(screen.getByText("spot upstream request failed")).toBeInTheDocument();
    expect(screen.getByLabelText("导入对应日期 JSON")).toBeEnabled();
  });
});
