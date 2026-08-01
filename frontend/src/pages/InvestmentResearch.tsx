import { useState } from "react";
import { AlertTriangle, BarChart3, BookOpenCheck, DatabaseZap, RefreshCw } from "lucide-react";

import { api, type ResearchMvpCandidate, type ResearchMvpFeishuPreview, type ResearchMvpHistoricalEvaluation, type ResearchMvpRun } from "@/lib/api";
import { cn } from "@/lib/utils";

const MARKET_TONE: Record<ResearchMvpRun["market_state"], string> = {
  NORMAL: "text-emerald-600",
  CAUTION: "text-amber-600",
  PANIC: "text-orange-600",
  EXTREME_PANIC: "text-red-600",
};

function formatNumber(value: number | null, suffix = "") {
  return value === null ? "Data Gap" : `${value.toFixed(2)}${suffix}`;
}

function formatBreadth(value: number | null) {
  return value === null ? "Data Gap" : `${(value * 100).toFixed(2)}%`;
}

function formatTurnover(value: number | null) {
  return value === null ? "Data Gap" : `${(value / 100_000_000).toFixed(2)} 亿元`;
}

function CandidateCard({ candidate }: { candidate: ResearchMvpCandidate }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="rounded-xl border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{candidate.name}</h3>
          <p className="font-mono text-xs text-muted-foreground">{candidate.code} · {candidate.sector}</p>
        </div>
        <span className="rounded-full border bg-muted px-3 py-1 text-xs font-semibold">
          研究评分 {candidate.score.toFixed(1)}
        </span>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="当前价格" value={formatNumber(candidate.current_price)} />
        <Metric label="距一年高点" value={formatNumber(candidate.drawdown_pct, "%")} />
        <Metric label="相对大盘" value={formatNumber(candidate.relative_to_market_pct, "%")} />
        <Metric label="行业表现" value={formatNumber(candidate.sector_performance_pct, "%")} />
        <Metric label="研究状态" value={candidate.research_status} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h4 className="text-sm font-semibold">入选原因</h4>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            {candidate.selection_reasons.length > 0
              ? candidate.selection_reasons.map((reason) => <li key={reason}>· {reason}</li>)
              : <li>· Data Gap：暂无完整入选证据。</li>}
          </ul>
        </div>
        <div>
          <h4 className="text-sm font-semibold">风险</h4>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            <li>· 首要否定问题：{candidate.first_rejection}</li>
            {candidate.risks.map((risk) => <li key={risk}>· {risk}</li>)}
          </ul>
        </div>
      </div>
      {candidate.data_gaps.length > 0 && (
        <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          Data Gap：{candidate.data_gaps.join("、")}
        </p>
      )}
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="mt-4 rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted"
      >
        {expanded ? "收起研究详情" : "查看研究详情"}
      </button>
      {expanded && (
        <div className="mt-4 space-y-5 border-t pt-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <DetailMetrics title="公司质量" values={candidate.quality} />
            <DetailMetrics title="财务信息" values={candidate.financials} />
            <DetailMetrics title="估值信息" values={candidate.valuation} />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <DetailList title="支持证据" items={candidate.supporting_evidence} />
            <DetailList title="反方证据" items={candidate.counter_evidence} />
            <DetailList title="潜在风险" items={candidate.risks} />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <DetailList title="市场原因" items={candidate.entry_reasons.market} />
            <DetailList title="公司原因" items={candidate.entry_reasons.company} />
            <DetailList title="估值原因" items={candidate.entry_reasons.valuation} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <DetailList title="催化剂" items={candidate.catalysts} />
            <DetailList title="失效条件" items={candidate.invalidation} />
          </div>
          <section className="rounded-lg border bg-background p-4">
            <h4 className="font-semibold">Research Plan</h4>
            <div className="mt-3 grid gap-4 lg:grid-cols-3">
              <DetailList title="观察条件：什么情况下值得进一步关注" items={candidate.research_plan.observation_conditions} />
              <DetailList title="风险条件：什么情况下判断错误" items={candidate.research_plan.risk_conditions} />
              <DetailList title="验证条件：未来如何验证判断" items={candidate.research_plan.validation_conditions} />
            </div>
          </section>
        </div>
      )}
    </article>
  );
}

function DetailList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4 className="text-sm font-semibold">{title}</h4>
      <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
        {items.length > 0 ? items.map((item) => <li key={item}>· {item}</li>) : <li>· Data Gap</li>}
      </ul>
    </div>
  );
}

function DetailMetrics({ title, values }: { title: string; values: Record<string, number | null> }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <h4 className="text-sm font-semibold">{title}</h4>
      <dl className="mt-2 space-y-1 text-xs text-muted-foreground">
        {Object.entries(values).map(([key, value]) => (
          <div key={key} className="flex justify-between gap-3"><dt>{key}</dt><dd>{value ?? "Data Gap"}</dd></div>
        ))}
      </dl>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/60 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold">{value}</p>
    </div>
  );
}

export function InvestmentResearch() {
  const [report, setReport] = useState<ResearchMvpRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [historyDate, setHistoryDate] = useState("2025-04-07");
  const [history, setHistory] = useState<ResearchMvpHistoricalEvaluation | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [feishu, setFeishu] = useState<ResearchMvpFeishuPreview | null>(null);

  const generate = async () => {
    setLoading(true);
    setError("");
    try {
      setReport(await api.runInvestmentResearch());
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成盘后研究失败");
    } finally {
      setLoading(false);
    }
  };

  const evaluateHistory = async () => {
    setHistoryLoading(true);
    setError("");
    try {
      setHistory(await api.evaluateInvestmentResearchHistory(historyDate));
    } catch (err) {
      setError(err instanceof Error ? err.message : "历史验证失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  const previewFeishu = async () => {
    if (!report) return;
    setFeishu(await api.previewInvestmentResearchFeishu(report));
  };

  const confirmFeishu = async () => {
    if (!report) return;
    setFeishu(await api.previewInvestmentResearchFeishu(report, true, true));
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6 lg:p-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpenCheck className="h-7 w-7 text-primary" />
            <h1 className="text-2xl font-bold">投资研究</h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            基于最近完整交易日和既有观察池生成 Research Candidate，不输出交易指令。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void generate()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          {loading ? "正在生成" : "生成盘后研究"}
        </button>
      </header>

      {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{error}</div>}

      {!report && !error && (
        <section className="rounded-xl border border-dashed p-10 text-center text-muted-foreground">
          <DatabaseZap className="mx-auto mb-3 h-8 w-8" />
          点击“生成盘后研究”开始真实数据研究运行。
        </section>
      )}

      {report && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
            <Metric label="交易日" value={report.trade_date} />
            <div className="rounded-lg bg-muted/60 p-3">
              <p className="text-xs text-muted-foreground">市场状态</p>
              <p className={cn("mt-1 font-bold", MARKET_TONE[report.market_state])}>{report.market_state}</p>
            </div>
            <Metric label="上涨家数" value={formatNumber(report.market_summary.advancers)} />
            <Metric label="下跌家数" value={formatNumber(report.market_summary.decliners)} />
            <Metric label="涨停数量" value={formatNumber(report.market_summary.limit_up)} />
            <Metric label="跌停数量" value={formatNumber(report.market_summary.limit_down)} />
            <Metric label="成交额" value={formatTurnover(report.market_summary.turnover_amount)} />
          </section>

          <section className="rounded-xl border bg-card p-5">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              <h2 className="font-semibold">市场宽度与恐慌原因</h2>
            </div>
            <p className="mt-3 text-sm">市场宽度：{formatBreadth(report.market_summary.breadth)}</p>
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {report.market_summary.panic_reasons.map((reason) => <li key={reason}>· {reason}</li>)}
            </ul>
            {report.data_gaps.length > 0 && <p className="mt-3 text-xs text-amber-700">Data Gap：{report.data_gaps.join("、")}</p>}
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-primary" />
              <h2 className="text-xl font-bold">Top 5 Research Candidate</h2>
            </div>
            {report.candidates.length > 0
              ? report.candidates.map((candidate) => <CandidateCard key={candidate.code} candidate={candidate} />)
              : <div className="rounded-xl border p-5 text-sm text-muted-foreground">当前没有候选；零候选是有效研究结果。</div>}
          </section>

          <section className="rounded-xl border bg-card p-5">
            <h2 className="font-semibold">飞书通知 Preview</h2>
            <p className="mt-1 text-sm text-muted-foreground">默认 send=false、scheduler=false；确认后仅加入既有通知发件箱。</p>
            <button type="button" onClick={() => void previewFeishu()} className="mt-3 rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted">生成飞书 Preview</button>
            {feishu && (
              <div className="mt-3 space-y-3">
                <pre className="whitespace-pre-wrap rounded-lg bg-muted p-4 text-xs">{feishu.preview}</pre>
                {feishu.status === "preview" && feishu.eligible && <button type="button" onClick={() => void confirmFeishu()} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">确认加入飞书发件箱</button>}
                {feishu.status === "preview" && !feishu.eligible && <p className="text-xs text-muted-foreground">仅 PANIC/EXTREME_PANIC 且存在高质量候选时可加入发件箱。</p>}
                {feishu.status !== "preview" && <p className="text-sm text-emerald-700">飞书状态：{feishu.status}</p>}
              </div>
            )}
          </section>
        </>
      )}

      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">历史验证</h2>
        <p className="mt-1 text-sm text-muted-foreground">仅使用所选日期已保存的时点快照；缺失时不以当前候选回填。</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input type="date" value={historyDate} onChange={(event) => setHistoryDate(event.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm" />
          <button type="button" onClick={() => void evaluateHistory()} disabled={historyLoading} className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-60">
            {historyLoading ? "验证中" : "查看历史验证"}
          </button>
        </div>
        {history && (
          <div className="mt-4">
            <p className="text-sm">当时市场状态：{history.market_state ?? "Data Gap"}</p>
            {history.data_gaps.length > 0 && <p className="mt-2 text-xs text-amber-700">Data Gap：{history.data_gaps.join("、")}</p>}
            {history.candidates.length > 0 && (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead><tr className="border-b"><th className="p-2">候选</th><th className="p-2">T+5</th><th className="p-2">T+20</th><th className="p-2">T+60</th></tr></thead>
                  <tbody>{history.candidates.map((candidate) => (
                    <tr key={candidate.code} className="border-b">
                      <td className="p-2">{candidate.name} ({candidate.code})</td>
                      {([5, 20, 60] as const).map((horizon) => (
                        <td key={horizon} className="p-2">
                          <div>{formatNumber(candidate[`t${horizon}`], "%")}</div>
                          <div className="text-xs text-muted-foreground">
                            {candidate[`t${horizon}_outcome`]} · 超额 {formatNumber(candidate[`t${horizon}_excess`], "%")} · 回撤 {formatNumber(candidate[`t${horizon}_max_drawdown`], "%")}
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
