import { fireEvent, render, screen } from "@testing-library/react";

import type { ResearchMvpRun } from "@/lib/api";
import { InvestmentResearch } from "../InvestmentResearch";

const apiMock = vi.hoisted(() => ({ runInvestmentResearch: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiMock }));

const report: ResearchMvpRun = {
  trade_date: "2026-07-24",
  market_state: "PANIC",
  market_summary: {
    advancers: 512,
    decliners: 4210,
    limit_up: 31,
    limit_down: 106,
    breadth: 0.1084,
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
    risks: ["盈利持续性仍需验证"],
    data_gaps: ["relative_to_market_pct"],
    score: 81,
    research_status: "A - 深入研究",
    first_rejection: "需要验证盈利持续性",
    quality: { score: 20, roe_5y_median_pct: 12 },
    financials: { revenue_growth_pct: 18 },
    valuation: { pe_ttm: 28 },
    supporting_evidence: ["距一年高点回撤31.5%"],
    counter_evidence: [],
  }],
  data_gaps: [],
};

describe("InvestmentResearch page", () => {
  beforeEach(() => {
    apiMock.runInvestmentResearch.mockReset();
    apiMock.runInvestmentResearch.mockResolvedValue(report);
  });

  it("calls the real Research MVP API only after the user generates a report", async () => {
    render(<InvestmentResearch />);
    expect(apiMock.runInvestmentResearch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "生成盘后研究" }));

    expect(await screen.findByText("中芯国际")).toBeInTheDocument();
    expect(apiMock.runInvestmentResearch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("PANIC")).toBeInTheDocument();
    expect(screen.getByText("4210.00")).toBeInTheDocument();
    expect(screen.getByText("Top 5 Research Candidate")).toBeInTheDocument();
    expect(screen.getByText(/Data Gap：relative_to_market_pct/)).toBeInTheDocument();
  });
});
