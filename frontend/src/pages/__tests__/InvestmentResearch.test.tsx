import { render, screen } from "@testing-library/react";

import type { InvestmentResearchStatus, InvestmentResearchThesis } from "@/lib/api";
import { InvestmentResearch } from "../InvestmentResearch";


const apiMock = vi.hoisted(() => ({
  getInvestmentResearchStatus: vi.fn(),
  listInvestmentResearchTheses: vi.fn(),
  listInvestmentResearchEvidenceInbox: vi.fn(),
  listInvestmentResearchEvidenceReadiness: vi.fn(),
  getInvestmentResearchDaily: vi.fn(),
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
  });

  it("shows evidence initialization without inventing confidence", async () => {
    render(<InvestmentResearch />);
    expect(await screen.findByText("AI Investment Researcher")).toBeInTheDocument();
    expect(screen.getByText("AI Industry")).toBeInTheDocument();
    expect(screen.getByText("证据就绪度：缺少反方证据")).toBeInTheDocument();
    expect(screen.getByText(/What is the strongest evidence/)).toBeInTheDocument();
    expect(screen.getByText("等待证据初始化")).toBeInTheDocument();
    expect(screen.getByText(/未初始化节点不显示 Confidence/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows a truthful empty daily state and read-only boundary", async () => {
    render(<InvestmentResearch />);
    expect(await screen.findByText(/今日完整日报尚未生成/)).toBeInTheDocument();
    expect(screen.getByText(/V2 自动研究当前关闭/)).toBeInTheDocument();
    expect(screen.getByText("Research Candidate，不是交易指令")).toBeInTheDocument();
    expect(screen.getByText("当前没有待审证据。")).toBeInTheDocument();
    expect(screen.getByText("当前没有已接受证据。")).toBeInTheDocument();
  });
});
