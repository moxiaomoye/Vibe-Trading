import { fireEvent, render, screen } from "@testing-library/react";
import { ValueHunter } from "../ValueHunter";
import type { ValueHunterScan, ValueHunterStatus } from "@/lib/api";

const apiMock = vi.hoisted(() => ({
  getValueHunterStatus: vi.fn(),
  runValueHunter: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiMock }));

const scan: ValueHunterScan = {
  run_id: "run-1", started_at: "2026-07-20T10:00:00Z", completed_at: "2026-07-20T10:00:01Z", mode: "demo",
  market: {
    observation: { as_of: "2026-07-20", source: "fixture", warnings: [], indices: [] },
    score: 88, level: "股灾", components: { trend: 30, drawdown: 22, breadth: 20, panic: 16 },
    reasons: ["主要指数破位", "市场宽度恶化"],
  },
  candidates: [{
    observation: { symbol: "688001", name: "示例芯片龙头", sector: "半导体", theme: "国产芯片", warnings: [] },
    score: { quality: 22, valuation: 20, fundamentals: 18, dislocation: 13, risk_cleanliness: 15, total: 88 },
    bucket: "价值错杀", status: "A - 深入研究", reasons: ["行业龙头", "估值历史低位"],
    first_rejection: "验证盈利持续性", missing_fields: [],
  }],
  notification_required: true, notification_reason: "达到阈值", errors: [],
};

const status: ValueHunterStatus = {
  enabled: true, provider: "demo", schedule: "18:10", timezone: "Asia/Shanghai",
  notification_channels: ["feishu", "email"], notification_ready: true,
  missing_notification_settings: [], latest: scan,
};

describe("ValueHunter page", () => {
  beforeEach(() => {
    apiMock.getValueHunterStatus.mockReset();
    apiMock.runValueHunter.mockReset();
    apiMock.getValueHunterStatus.mockResolvedValue(status);
  });

  it("renders market evidence, candidate bucket, and rejection test", async () => {
    render(<ValueHunter />);
    expect(await screen.findByText("Value Hunter")).toBeInTheDocument();
    expect(screen.getByText(/股灾 88.0\/100/)).toBeInTheDocument();
    expect(screen.getByText("示例芯片龙头")).toBeInTheDocument();
    expect(screen.getByText("价值错杀")).toBeInTheDocument();
    expect(screen.getByText(/验证盈利持续性/)).toBeInTheDocument();
    expect(screen.getByText(/不执行交易/)).toBeInTheDocument();
  });

  it("manual scan explicitly keeps external notification disabled", async () => {
    apiMock.runValueHunter.mockResolvedValue(scan);
    render(<ValueHunter />);
    await screen.findByText("示例芯片龙头");
    fireEvent.click(screen.getByRole("button", { name: "立即扫描" }));
    await screen.findByText("示例芯片龙头");
    expect(apiMock.runValueHunter).toHaveBeenCalledWith(false);
  });
});
