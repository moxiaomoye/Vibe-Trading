import { useState } from "react";
import { AlertTriangle, BarChart3, BookOpenCheck, DatabaseZap, RefreshCw } from "lucide-react";

import { api, AUTH_REQUIRED_MESSAGE, type ResearchMvpCandidate, type ResearchMvpFeishuPreview, type ResearchMvpHistoricalEvaluation, type ResearchMvpRun } from "@/lib/api";
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

function formatPriceRange(low: number | null, high: number | null) {
  return low === null || high === null ? "Data Gap" : `${low.toFixed(4)} ～ ${high.toFixed(4)}`;
}

function DataGapSummary({ gaps, className = "" }: { gaps: string[]; className?: string }) {
  if (gaps.length === 0) return null;
  const blockingPattern = /price|nav|trade_date|market_summary|base_trade_date|行情|净值/i;
  const qualityPattern = /valuation|roe|cashflow|profit|revenue|pe_|pb|relative|sector|估值|财务|行业/i;
  const groups = [
    { label: "阻断判断", items: gaps.filter((gap) => blockingPattern.test(gap)) },
    { label: "降低可信度", items: gaps.filter((gap) => !blockingPattern.test(gap) && qualityPattern.test(gap)) },
    { label: "补充信息", items: gaps.filter((gap) => !blockingPattern.test(gap) && !qualityPattern.test(gap)) },
  ].filter((group) => group.items.length > 0);
  return (
    <div className={cn("space-y-1 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800", className)}>
      {groups.map((group) => <p key={group.label}><span className="font-semibold">{group.label}：</span>{group.items.join("、")}</p>)}
    </div>
  );
}

function EtfValuationPanel({ candidate }: { candidate: ResearchMvpCandidate }) {
  const value = candidate.etf_valuation;
  if (!value) {
    return <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">ETF估值 Data Gap：净值与历史价格依据尚未取得。</p>;
  }
  return (
    <section className="mt-4 rounded-lg border bg-background p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-semibold">ETF 研究价格区间</h4>
        <span className="rounded-full border bg-muted px-3 py-1 text-xs font-semibold">{value.valuation_state ?? "Data Gap"}</span>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="最新单位净值" value={formatNumber(value.latest_nav)} />
        <Metric label="ETF净值溢价" value={formatNumber(value.nav_premium_pct, "%")} />
        <Metric label="合理价格区间" value={formatPriceRange(value.reasonable_price_low, value.reasonable_price_high)} />
        <Metric label="低估关注区间" value={formatPriceRange(value.bargain_price_low, value.bargain_price_high)} />
        <Metric label="深度低估参考" value={value.deep_value_below === null ? "Data Gap" : `≤ ${value.deep_value_below.toFixed(4)}`} />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        ETF交易溢价用于比较市价与最新可得净值；底层指数：{value.underlying_index_name ?? "Data Gap"}（{value.underlying_index_code ?? "Data Gap"}）；
        PE：{formatNumber(value.underlying_pe ?? null)}；指数估值相对近期中位数：{formatNumber(value.underlying_valuation_premium_pct, "%")}（{value.underlying_valuation_state ?? "Data Gap"}）。
        区间口径：{value.valuation_method ?? "Data Gap"}；净值日期：{value.nav_as_of ?? "Data Gap"}；置信度：{value.confidence ?? "Data Gap"}。
      </p>
      {value.underlying_history_sessions != null && (
        <p className="mt-2 text-xs text-muted-foreground">底层估值样本：{value.underlying_history_sessions}个可得交易日，截至{value.underlying_valuation_as_of ?? "Data Gap"}；短样本仅作筛选，不等同内在价值。</p>
      )}
      {value.premium_reliability === "limited_qdii_stale_nav" && (
        <p className="mt-2 text-xs text-amber-700">QDII净值受海外时差、汇率与披露滞后影响，当前溢价仅作研究筛选。</p>
      )}
    </section>
  );
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
      {candidate.security_type === "etf" && <EtfValuationPanel candidate={candidate} />}
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
      <DataGapSummary gaps={candidate.data_gaps} className="mt-4" />
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
  const [panicSensitivity, setPanicSensitivity] = useState(50);
  const watchlistScan = report?.market_summary.watchlist_scan ?? [];

  const generate = async () => {
    setLoading(true);
    setError("");
    try {
      setReport(await api.runInvestmentResearch(panicSensitivity));
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

      <section className="rounded-xl border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">恐慌敏感度</h2>
            <p className="mt-1 text-sm text-muted-foreground">数值越低越敏感，越高越强调多项指标共同确认。</p>
          </div>
          <span className="rounded-full border bg-muted px-3 py-1 text-sm font-semibold">
            {panicSensitivity <= 30 ? "敏感" : panicSensitivity <= 70 ? "平衡" : "严谨"} · {panicSensitivity}
          </span>
        </div>
        <input
          aria-label="恐慌敏感度"
          type="range"
          min="0"
          max="100"
          step="1"
          value={panicSensitivity}
          onChange={(event) => setPanicSensitivity(Number(event.target.value))}
          className="mt-4 w-full accent-primary"
        />
        <div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>敏感</span><span>平衡</span><span>严谨</span></div>
        {report && (
          <p className="mt-3 text-xs text-muted-foreground">
            本次阈值：指数 ≤ {report.panic_sensitivity.index_daily_return_pct}% · 上涨占比 ≤ {(report.panic_sensitivity.max_advancer_ratio * 100).toFixed(1)}% · 跌停 ≥ {report.panic_sensitivity.min_limit_down_count} · 已触发 {report.panic_sensitivity.trigger_count}/{report.panic_sensitivity.required_confirmations} 项
          </p>
        )}
      </section>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <p>{error}</p>
          {error === AUTH_REQUIRED_MESSAGE && <a href="/settings" className="mt-3 inline-block rounded-md border border-destructive/30 px-3 py-2 font-medium hover:bg-destructive/10">前往设置</a>}
        </div>
      )}

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
            <DataGapSummary gaps={report.data_gaps} className="mt-3" />
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
            <h2 className="font-semibold">观察池扫描结果</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              共扫描 {watchlistScan.length} 只；Top 5 之外仍保留未入选原因和数据日期。
            </p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead><tr className="border-b"><th className="p-2">标的</th><th className="p-2">评分</th><th className="p-2">结果</th><th className="p-2">数据状态</th><th className="p-2">说明</th></tr></thead>
                <tbody>{watchlistScan.map((item) => (
                  <tr key={item.code} className="border-b align-top">
                    <td className="p-2"><div>{item.name}</div><div className="font-mono text-xs text-muted-foreground">{item.code} · {item.security_type.toUpperCase()}</div></td>
                    <td className="p-2">{item.score.toFixed(1)}</td>
                    <td className="p-2">{item.selected ? "Top 5" : item.research_status}</td>
                    <td className="p-2"><div>{item.data_status === "available" ? "可用" : item.data_status === "stale" ? "陈旧" : "缺失"}</div><div className="text-xs text-muted-foreground">{item.data_as_of ?? "Data Gap"} · {item.data_source ?? "Data Gap"}</div></td>
                    <td className="p-2 text-xs text-muted-foreground">{item.exclusion_reason ?? "已进入 Research Candidate"}{item.data_gaps.length > 0 ? `；Data Gap ${item.data_gaps.length} 项` : ""}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border bg-card p-5">
            <h2 className="font-semibold">飞书通知 Preview</h2>
            <p className="mt-1 text-sm text-muted-foreground">默认 send=false、scheduler=false；确认后通过既有通知发件箱立即投递一次。</p>
            <button type="button" onClick={() => void previewFeishu()} className="mt-3 rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted">生成飞书 Preview</button>
            {feishu && (
              <div className="mt-3 space-y-3">
                <pre className="whitespace-pre-wrap rounded-lg bg-muted p-4 text-xs">{feishu.preview}</pre>
                {feishu.status === "preview" && feishu.eligible && <button type="button" onClick={() => void confirmFeishu()} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">确认并发送飞书</button>}
                {feishu.status === "preview" && !feishu.eligible && <p className="text-xs text-muted-foreground">仅 PANIC/EXTREME_PANIC 且存在高质量候选时可加入发件箱。</p>}
                {feishu.status !== "preview" && <p className={cn("text-sm", feishu.status === "delivered" ? "text-emerald-700" : "text-red-700")}>飞书状态：{feishu.status === "delivered" ? "已发送" : feishu.status}</p>}
                {feishu.delivery_error && <p className="text-xs text-red-700">{feishu.delivery_error}</p>}
              </div>
            )}
          </section>
        </>
      )}

      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">历史验证</h2>
        <p className="mt-1 text-sm text-muted-foreground">优先使用所选日期已保存的时点快照；缺失时从公开时点数据重建（不含未来信息）并自动保存，重建耗时约 1-2 分钟。</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input type="date" value={historyDate} onChange={(event) => setHistoryDate(event.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm" />
          <button type="button" onClick={() => void evaluateHistory()} disabled={historyLoading} className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-60">
            {historyLoading ? "验证中" : "查看历史验证"}
          </button>
        </div>
        {history && (
          <div className="mt-4">
            <p className="text-sm">当时市场状态：{history.market_state ?? "Data Gap"}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              当时恐慌标准：{history.panic_sensitivity ? `${history.panic_sensitivity.label} · ${history.panic_sensitivity.value}（触发 ${history.panic_sensitivity.trigger_count}/${history.panic_sensitivity.required_confirmations}）` : "Data Gap"}
            </p>
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
