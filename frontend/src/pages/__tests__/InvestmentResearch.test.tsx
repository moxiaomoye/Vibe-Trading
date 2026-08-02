import { fireEvent, render, screen } from "@testing-library/react";

import type { ResearchMvpRun } from "@/lib/api";
import { InvestmentResearch } from "../InvestmentResearch";

const apiMock = vi.hoisted(() => ({
  runInvestmentResearch: vi.fn(), evaluateInvestmentResearchHistory: vi.fn(), previewInvestmentResearchFeishu: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiMock }));

const report: ResearchMvpRun = {
  trade_date: "2026-07-24",
  market_state: "PANIC",
  panic_sensitivity: {
    value: 50,
    label: "平衡",
    index_daily_return_pct: -2.25,
    max_advancer_ratio: 0.35,
    min_limit_down_count: 43,
    required_confirmations: 2,
    trigger_count: 3,
    config_version: 2,
    checks: {},
  },
  market_summary: {
    advancers: 512,
    decliners: 4210,
    limit_up: 31,
    limit_down: 106,
    breadth: 0.1084,
    turnover_amount: 1_234_000_000_000,
    panic_reasons: ["市场宽度显著收缩"],
    source: "AKShare/Eastmoney",
  },
  candidates: [{
    name: "中芯国际",
    code: "688981",
    current_price: 82.4,
    drawdown_pct: -31.5,
    relative_to_market_pct: null,
    sector: "半导体",
    sector_performance_pct: -8.2,
    selection_reasons: ["距一年高点回撤31.5%"],
    entry_reasons: { market: ["市场回撤"], company: ["ROE稳定"], valuation: ["历史低分位"] },
    risks: ["盈利持续性仍需验证"],
    catalysts: ["下一期财报验证"],
    invalidation: ["现金流持续恶化"],
    data_gaps: ["relative_to_market_pct"],
    score: 81,
    research_status: "A - 深入研究",
    first_rejection: "需要验证盈利持续性",
    quality: { score: 20, roe_5y_median_pct: 12 },
    financials: { revenue_growth_pct: 18 },
    valuation: { pe_ttm: 28 },
    etf_valuation: null,
    supporting_evidence: ["距一年高点回撤31.5%"],
    counter_evidence: [],
    forward_validation: { t5: null, t20: null, t60: null },
    research_plan: {
      observation_conditions: ["收入与利润趋势保持稳定"],
      risk_conditions: ["现金流持续恶化"],
      validation_conditions: ["下一次定期报告后复核"],
    },
  }],
  data_gaps: [],
};

describe("InvestmentResearch page", () => {
  beforeEach(() => {
    apiMock.runInvestmentResearch.mockReset();
    apiMock.runInvestmentResearch.mockResolvedValue(report);
    apiMock.evaluateInvestmentResearchHistory.mockReset();
    apiMock.evaluateInvestmentResearchHistory.mockResolvedValue({
      trade_date: "2025-04-07", market_state: "PANIC",
      candidates: [{
        name: "中芯国际", code: "688981", research_status: "Research",
        t5: 3.2, t20: 8.1, t60: null,
        t5_max_drawdown: -1.2, t20_max_drawdown: -4.5, t60_max_drawdown: null,
        t5_excess: 2.1, t20_excess: 5.2, t60_excess: null,
        t5_outcome: "不确定", t20_outcome: "正确", t60_outcome: "不确定",
        data_gaps: ["t60"],
      }],
      data_gaps: ["688981.t60"],
    });
    apiMock.previewInvestmentResearchFeishu.mockReset();
    apiMock.previewInvestmentResearchFeishu
      .mockResolvedValueOnce({ preview: "盘后研究 Preview", send: false, confirmed: false, scheduler: false, status: "preview", eligible: true })
      .mockResolvedValueOnce({ preview: "盘后研究 Preview", send: true, confirmed: true, scheduler: false, status: "queued", message_id: "message-1", eligible: true });
  });

  it("shows ETF fair, bargain and NAV premium research fields", async () => {
    apiMock.runInvestmentResearch.mockResolvedValueOnce({
      ...report,
      candidates: [{
        ...report.candidates[0],
        name: "科创50ETF",
        code: "588060",
        security_type: "etf",
        etf_valuation: {
          latest_nav: 1.039,
          nav_as_of: "2026-07-31",
          nav_market_price: 1.04,
          nav_premium_pct: 0.096,
          nav_source: "AKShare/Eastmoney",
          premium_reliability: "latest_available_nav",
          reasonable_price_low: 0.98,
          reasonable_price_high: 1.08,
          bargain_price_low: 0.88,
          bargain_price_high: 0.95,
          deep_value_below: 0.88,
          historical_price_percentile: 0.52,
          underlying_valuation_premium_pct: null,
          valuation_state: "历史合理区间",
          valuation_method: "近252个交易日市场价格分位（研究筛选口径）",
          confidence: "screen_grade",
          price_as_of: "2026-07-31",
          price_source: "akshare",
          history_sessions: 252,
        },
      }],
    });
    render(<InvestmentResearch />);
    fireEvent.click(screen.getByRole("button", { name: "生成盘后研究" }));

    expect(await screen.findByText("ETF 研究价格区间")).toBeInTheDocument();
    expect(screen.getByText("0.10%")).toBeInTheDocument();
    expect(screen.getByText("0.9800 ～ 1.0800")).toBeInTheDocument();
    expect(screen.getByText("0.8800 ～ 0.9500")).toBeInTheDocument();
  });

  it("calls the real Research MVP API only after the user generates a report", async () => {
    render(<InvestmentResearch />);
    expect(apiMock.runInvestmentResearch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "生成盘后研究" }));

    expect(await screen.findByText("中芯国际")).toBeInTheDocument();
    expect(apiMock.runInvestmentResearch).toHaveBeenCalledWith(50);
    expect(screen.getByText("PANIC")).toBeInTheDocument();
    expect(screen.getByText("4210.00")).toBeInTheDocument();
    expect(screen.getByText("Top 5 Research Candidate")).toBeInTheDocument();
    expect(screen.getByText((_, element) => (
      element?.tagName === "P"
      && element.textContent?.includes("降低可信度：relative_to_market_pct") === true
    ))).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看研究详情" }));
    expect(screen.getByText("公司质量")).toBeInTheDocument();
    expect(screen.getByText("支持证据")).toBeInTheDocument();
    expect(screen.getByText("反方证据")).toBeInTheDocument();
    expect(screen.getByText("Research Plan")).toBeInTheDocument();
    expect(screen.getByText("催化剂")).toBeInTheDocument();
    expect(screen.getByText("失效条件")).toBeInTheDocument();
    expect(screen.getByText("观察条件：什么情况下值得进一步关注")).toBeInTheDocument();
    expect(screen.getByText("风险条件：什么情况下判断错误")).toBeInTheDocument();
    expect(screen.getByText("验证条件：未来如何验证判断")).toBeInTheDocument();
  });

  it("sends the selected panic sensitivity and displays resolved thresholds", async () => {
    render(<InvestmentResearch />);
    fireEvent.change(screen.getByRole("slider", { name: "恐慌敏感度" }), {
      target: { value: "80" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成盘后研究" }));

    await screen.findByText("中芯国际");
    expect(apiMock.runInvestmentResearch).toHaveBeenCalledWith(80);
    expect(screen.getByText(/本次阈值：指数/)).toBeInTheDocument();
  });

  it("shows point-in-time historical outcomes without filling unavailable horizons", async () => {
    render(<InvestmentResearch />);
    fireEvent.click(screen.getByRole("button", { name: "查看历史验证" }));
    expect(await screen.findByText("当时市场状态：PANIC")).toBeInTheDocument();
    expect(apiMock.evaluateInvestmentResearchHistory).toHaveBeenCalledWith("2025-04-07");
    expect(screen.getByText("3.20%")).toBeInTheDocument();
    expect(screen.getAllByText("Data Gap").length).toBeGreaterThan(0);
  });

  it("previews before an explicit Feishu outbox confirmation", async () => {
    render(<InvestmentResearch />);
    fireEvent.click(screen.getByRole("button", { name: "生成盘后研究" }));
    await screen.findByText("中芯国际");
    fireEvent.click(screen.getByRole("button", { name: "生成飞书 Preview" }));
    expect(await screen.findByText("盘后研究 Preview")).toBeInTheDocument();
    expect(apiMock.previewInvestmentResearchFeishu).toHaveBeenLastCalledWith(report);
    fireEvent.click(screen.getByRole("button", { name: "确认加入飞书发件箱" }));
    expect(await screen.findByText("飞书状态：queued")).toBeInTheDocument();
    expect(apiMock.previewInvestmentResearchFeishu).toHaveBeenLastCalledWith(report, true, true);
  });
});
