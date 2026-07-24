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

vi.mock("@/lib/api", () => ({ api: apiMock }));

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
    expect(await screen.findByRole("button", { name: "生成今日盘后报告" })).toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole("button", { name: "生成今日盘后报告" }));

    await waitFor(() => expect(apiMock.runCurrentPanicShadowReport).toHaveBeenCalledTimes(1));
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

    fireEvent.change(await screen.findByLabelText("导入当日 JSON"), {
      target: {
        files: [
          new File([JSON.stringify(manifest)], "post-close.json", {
            type: "application/json",
          }),
        ],
      },
    });

    await waitFor(() => {
      expect(apiMock.runManualPanicShadowReport).toHaveBeenCalledWith(manifest);
    });
    expect(await screen.findByText("correction")).toBeInTheDocument();
    expect(screen.getByText(/imported universe only/)).toBeInTheDocument();
  });
});
