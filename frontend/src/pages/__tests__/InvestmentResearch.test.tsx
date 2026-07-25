import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { InvestmentResearchStatus, InvestmentResearchThesis } from "@/lib/api";
import { InvestmentResearch } from "../InvestmentResearch";


const apiMock = vi.hoisted(() => ({
  getInvestmentResearchStatus: vi.fn(),
  listInvestmentResearchTheses: vi.fn(),
  listInvestmentResearchEvidenceInbox: vi.fn(),
  listInvestmentResearchEvidenceReadiness: vi.fn(),
  getInvestmentResearchDaily: vi.fn(),
  getPanicShadowStatus: vi.fn(),
  getLatestPanicShadowReport: vi.fn(),
  runCurrentPanicShadowReport: vi.fn(),
  runManualPanicShadowReport: vi.fn(),
  runPanicShadowReport: vi.fn(),
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
    apiMock.getInvestmentResearchStatus.mockResolvedValue(status);
    apiMock.listInvestmentResearchTheses.mockResolvedValue(theses);
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
