import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bot,
  BookOpenCheck,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Gauge,
  Eye,
  FileCheck2,
  FlaskConical,
  Landmark,
  Newspaper,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  WalletCards,
} from "lucide-react";

import {
  ApiError,
  api,
  isDisabledFeatureError,
  type InvestmentResearchDailyReport,
  type DailyOpportunityReport,
  type DailyOpportunityStatus,
  type InvestmentResearchEvidenceInboxItem,
  type InvestmentResearchEvidenceReadiness,
  type HistoricalEvaluationReport,
  type InvestmentResearchStatus,
  type InvestmentResearchThesis,
  type ManualThesisInitializationRequest,
  type PanicShadowDateMode,
  type WatchlistThesisInitializationStatus,
  type WatchlistThesisStarter,
} from "@/lib/api";
import {
  panicResearchDisabled,
  panicResearchError,
  panicResearchReady,
  type PanicResearchViewState,
} from "@/lib/panicResearchContract";


const SCOPE_LABELS: Record<InvestmentResearchThesis["scope"], string> = {
  macro: "宏观",
  theme: "主题",
  industry: "行业",
  value_chain: "产业链",
  company: "公司",
};

const DISPOSITION_LABELS = {
  evidence_gap: "需要补充证据",
  attribution_required: "需要解释价格变化",
  opportunity_review: "进入机会评审",
};

const READINESS_LABELS: Record<InvestmentResearchEvidenceReadiness["verdict"], string> = {
  not_ready: "尚无已审证据",
  needs_support: "缺少支持证据",
  needs_counter: "缺少反方证据",
  needs_quality_review: "证据质量待复核",
  ready_for_human_review: "可进入人工评审",
  approved_for_initialization: "已获准准备初始化",
};

function shanghaiDate(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function localDateTimeValue(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

function nonEmptyLines(value: string): string[] {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function latestPossibleT20Date(): string {
  const date = new Date(`${shanghaiDate()}T00:00:00Z`);
  let weekdays = 0;
  while (weekdays < 20) {
    date.setUTCDate(date.getUTCDate() - 1);
    const day = date.getUTCDay();
    if (day !== 0 && day !== 6) weekdays += 1;
  }
  return date.toISOString().slice(0, 10);
}

const ACTION_STYLES = {
  watch: "border-slate-200 bg-slate-50 text-slate-700",
  research: "border-amber-200 bg-amber-50 text-amber-800",
  prepare: "border-orange-300 bg-orange-50 text-orange-800",
  action_candidate: "border-red-300 bg-red-50 text-red-800",
};

function LegacyDailyOpportunitySection() {
  const [capability, setCapability] = useState<DailyOpportunityStatus | null>(null);
  const [report, setReport] = useState<DailyOpportunityReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const loadLatest = useCallback(async () => {
    try {
      setCapability(await api.getDailyOpportunityStatus());
      try {
        setReport(await api.getLatestDailyOpportunityReport());
      } catch (reason) {
        if (!(typeof reason === "object" && reason !== null && "status" in reason && reason.status === 404)) {
          throw reason;
        }
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取每日机会研究状态失败");
    }
  }, []);

  useEffect(() => { void loadLatest(); }, [loadLatest]);

  const run = useCallback(async () => {
    setRunning(true);
    setError("");
    try {
      setReport(await api.runDailyOpportunityReport());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "今日研究报告生成失败");
    } finally {
      setRunning(false);
    }
  }, []);

  return (
    <section className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="bg-gradient-to-r from-orange-50 via-amber-50 to-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-orange-600" />
              <h2 className="text-xl font-bold">今日自选机会研究</h2>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              每天固定研究中天科技与科创50ETF；任一恐慌条件触发，就提高研究优先级。
            </p>
          </div>
          <button
            type="button"
            onClick={() => { void run(); }}
            disabled={running}
            className="inline-flex items-center gap-2 rounded-lg bg-orange-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-orange-600 disabled:cursor-wait disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
            {running ? "正在获取并分析…" : "生成今日研究日报"}
          </button>
        </div>
        {capability && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border bg-white/80 px-3 py-1">标的60日跌幅 ≤ -30%</span>
            <span className="rounded-full border bg-white/80 px-3 py-1">上证60日下跌 ≥ 200点</span>
            <span className="rounded-full border bg-white/80 px-3 py-1">当日跌停 ≥ 1000只</span>
            <span className="rounded-full border bg-white/80 px-3 py-1">任意一项触发</span>
          </div>
        )}
      </div>

      {error && (
        <div className="mx-5 mt-5 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div><p className="font-medium">报告暂未生成</p><p className="mt-1">{error}</p></div>
        </div>
      )}

      {!report ? (
        <div className="p-8 text-center">
          <p className="font-medium">尚无每日研究报告</p>
          <p className="mt-1 text-sm text-muted-foreground">点击上方按钮，系统会自动获取真实行情；不会使用示例数据代替。</p>
        </div>
      ) : (
        <div className="space-y-5 p-5 sm:p-6">
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-xl border bg-muted/30 p-3">
              <p className="text-xs text-muted-foreground">报告日期</p>
              <p className="mt-1 font-semibold">{report.report_date}</p>
            </div>
            <div className="rounded-xl border bg-muted/30 p-3">
              <p className="text-xs text-muted-foreground">市场状态</p>
              <p className={`mt-1 font-semibold ${report.market.panic ? "text-red-600" : "text-emerald-600"}`}>
                {report.market.panic ? "市场恐慌" : "未触发市场恐慌"}
              </p>
            </div>
            <div className="rounded-xl border bg-muted/30 p-3">
              <p className="text-xs text-muted-foreground">上证60日变化</p>
              <p className="mt-1 font-semibold">
                {report.market.shanghai_60d_point_change === null
                  ? "数据缺失"
                  : `${report.market.shanghai_60d_point_change.toFixed(2)} 点`}
              </p>
            </div>
            <div className="rounded-xl border bg-muted/30 p-3">
              <p className="text-xs text-muted-foreground">当日跌停</p>
              <p className="mt-1 font-semibold">
                {report.market.limit_down_count === null ? "数据缺失" : `${report.market.limit_down_count} 只`}
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-orange-200 bg-orange-50/60 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-orange-700">今日结论</p>
            <p className="mt-1 text-base font-semibold">{report.conclusion}</p>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {report.assets.map((asset) => (
              <article key={asset.symbol} className="rounded-xl border bg-background p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-bold">{asset.name}</h3>
                    <p className="font-mono text-xs text-muted-foreground">
                      {asset.symbol} · {asset.asset_type === "etf" ? "ETF" : "股票"}
                    </p>
                  </div>
                  <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${ACTION_STYLES[asset.action_level]}`}>
                    {asset.action_label}
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="text-xs text-muted-foreground">最新收盘</p>
                    <p className="mt-1 font-semibold">{asset.latest_close ?? "—"}</p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="text-xs text-muted-foreground">60日涨跌</p>
                    <p className={`mt-1 font-semibold ${(asset.return_60d_pct ?? 0) <= -30 ? "text-red-600" : ""}`}>
                      {asset.return_60d_pct === null ? "—" : `${asset.return_60d_pct.toFixed(2)}%`}
                    </p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="text-xs text-muted-foreground">交易日期</p>
                    <p className="mt-1 text-sm font-semibold">{asset.effective_trade_date ?? "—"}</p>
                  </div>
                </div>

                <div className="mt-4">
                  <p className="flex items-center gap-1 text-sm font-semibold">
                    <TrendingDown className="h-4 w-4 text-orange-500" />触发依据
                  </p>
                  <ul className="mt-2 space-y-1 text-sm">
                    {asset.supporting_evidence.map((item) => (
                      <li key={item} className="rounded-md bg-muted/40 px-3 py-2">{item}</li>
                    ))}
                  </ul>
                </div>

                {asset.counter_evidence.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm font-semibold">尚未升级的原因</p>
                    <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-muted-foreground">
                      {asset.counter_evidence.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                )}

                <div className="mt-4 rounded-lg border border-dashed p-3 text-sm">
                  <p className="text-xs text-muted-foreground">下一步条件</p>
                  <p className="mt-1">{asset.next_condition}</p>
                </div>
              </article>
            ))}
          </div>

          {report.data_gaps.length > 0 && (
            <details className="rounded-lg border bg-muted/20 p-3 text-sm">
              <summary className="cursor-pointer font-medium">数据缺口与核验说明（{report.data_gaps.length}）</summary>
              <ul className="mt-2 list-inside list-disc space-y-1 text-muted-foreground">
                {report.data_gaps.map((gap) => <li key={gap}>{gap}</li>)}
              </ul>
            </details>
          )}

          <p className="text-xs text-muted-foreground">
            数据：{report.data_sources.prices}；只读研究，不发送通知、不启动调度、不执行交易。
          </p>
        </div>
      )}
    </section>
  );
}

void LegacyDailyOpportunitySection;

function signedPercent(value: number | null | undefined, digits = 2): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function compactMoney(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  const absolute = Math.abs(value);
  if (absolute >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`;
  if (absolute >= 10_000) return `${(value / 10_000).toFixed(1)}万`;
  return value.toFixed(0);
}

function valueTone(value: number | null | undefined): string {
  if (typeof value !== "number" || value === 0) return "text-slate-600";
  return value > 0 ? "text-emerald-600" : "text-rose-600";
}

function MetricTile({ label, value, detail, tone = "text-slate-950" }: {
  label: string;
  value: string;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className={`mt-2 text-xl font-bold tracking-tight ${tone}`}>{value}</p>
      {detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}
    </div>
  );
}

function DailyOpportunitySection() {
  const [capability, setCapability] = useState<DailyOpportunityStatus | null>(null);
  const [report, setReport] = useState<DailyOpportunityReport | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState("600522.SH");
  const [running, setRunning] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [notificationRunning, setNotificationRunning] = useState(false);
  const [notificationMessage, setNotificationMessage] = useState("");
  const [error, setError] = useState("");

  const loadLatest = useCallback(async () => {
    try {
      setCapability(await api.getDailyOpportunityStatus());
      try {
        const latest = await api.getLatestDailyOpportunityReport();
        setReport(latest);
        if (latest.assets.length > 0) setSelectedSymbol(latest.assets[0].symbol);
      } catch (reason) {
        if (!(reason instanceof ApiError && reason.status === 404)) throw reason;
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取每日研究状态失败");
    }
  }, []);

  useEffect(() => { void loadLatest(); }, [loadLatest]);

  const run = useCallback(async () => {
    setRunning(true);
    setError("");
    try {
      const next = await api.runDailyOpportunityReport();
      setReport(next);
      if (next.assets.length > 0) setSelectedSymbol(next.assets[0].symbol);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "今日研究报告生成失败");
    } finally {
      setRunning(false);
    }
  }, []);

  const askVibe = useCallback(async () => {
    if (!report?.agent_prompt) return;
    setAgentRunning(true);
    setError("");
    try {
      const session = await api.createSession(`自选股深度研判 ${report.report_date}`);
      await api.sendMessage(session.session_id, report.agent_prompt);
      window.location.assign(`/agent?session=${encodeURIComponent(session.session_id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Vibe深度研判启动失败");
      setAgentRunning(false);
    }
  }, [report]);

  const notify = useCallback(async () => {
    const channels = capability?.delivery?.configured_channels ?? [];
    if (!report || channels.length === 0) return;
    setNotificationRunning(true);
    setNotificationMessage("");
    setError("");
    try {
      const result = await api.notifyDailyOpportunityReport(channels);
      if (result.failed > 0) {
        setNotificationMessage(`发送完成：成功 ${result.delivered}，失败 ${result.failed}。失败消息已进入 Outbox 重试状态。`);
      } else if (result.duplicate_or_already_delivered > 0 && result.delivered === 0) {
        setNotificationMessage("今日同一份报告已经发送过，系统已阻止重复推送。");
      } else {
        setNotificationMessage(`已发送到 ${result.channels.join(" + ")}。`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究通知发送失败");
    } finally {
      setNotificationRunning(false);
    }
  }, [capability, report]);

  const selectedAsset = report?.assets.find((item) => item.symbol === selectedSymbol)
    ?? report?.assets[0]
    ?? null;
  const selected = selectedAsset ? {
    ...selectedAsset,
    return_5d_pct: selectedAsset.return_5d_pct ?? null,
    return_20d_pct: selectedAsset.return_20d_pct ?? null,
    relative_to_shanghai_20d_pct: selectedAsset.relative_to_shanghai_20d_pct ?? null,
    history_position: selectedAsset.history_position ?? {
      high: null, low: null, drawdown_from_high_pct: null, price_percentile: null,
    },
    technical: selectedAsset.technical ?? {
      ma20: null, ma60: null, ma120: null, rsi14: null,
      volatility20_annualized_pct: null, trend: "待更新", stabilization: false,
    },
    valuation: selectedAsset.valuation ?? {
      available: false, method: "生成新版报告后显示估值信息",
    },
    entry_framework: selectedAsset.entry_framework ?? {
      status: "wait" as const,
      label: selectedAsset.action_label,
      summary: "当前是旧版日报，请重新生成以获得条件式研究区间。",
      reasons: selectedAsset.supporting_evidence ?? [],
      conditions: [selectedAsset.next_condition],
      reference_zones: [],
      next_review_condition: selectedAsset.next_condition,
    },
    sectors: selectedAsset.sectors ?? [],
    news: selectedAsset.news ?? [],
  } : null;
  const style = report?.market.style_rotation ?? {
    bank_proxy: "512800.SH",
    technology_proxy: "588000.SH",
    bank_5d_return_pct: null,
    bank_20d_return_pct: null,
    technology_5d_return_pct: null,
    technology_20d_return_pct: null,
    bank_minus_technology_20d_pct: null,
    interpretation: "重新生成新版报告后显示银行与科技风格对比",
    state_support_inference: "仅凭价格相对强弱不能证明国家队护盘。",
  };

  const shadow = report?.shadow_portfolio ?? capability?.shadow_portfolio ?? null;
  const shadowLatest = shadow && shadow.daily_snapshots.length > 0
    ? shadow.daily_snapshots[shadow.daily_snapshots.length - 1]
    : null;

  return (
    <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-slate-50 shadow-xl shadow-slate-200/50">
      <div className="relative overflow-hidden bg-[radial-gradient(circle_at_top_right,_rgba(251,146,60,0.28),_transparent_34%),linear-gradient(135deg,#0f172a_0%,#172554_52%,#111827_100%)] px-5 py-7 text-white sm:px-7">
        <div className="absolute -left-20 -top-24 h-56 w-56 rounded-full bg-blue-500/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-orange-300">
              <Sparkles className="h-4 w-4" />
              Vibe Research Cockpit
            </div>
            <h2 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
              A股自选机会研究驾驶舱
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
              复用 Vibe 原有行情、财务、新闻、资金与行业工具。先判断市场环境，再判断估值和止跌条件，
              最后给出“研究区间”，不把下跌本身当作便宜。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-label="生成今日研究日报"
              onClick={() => { void run(); }}
              disabled={running}
              className="inline-flex items-center gap-2 rounded-xl bg-orange-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-orange-950/30 transition hover:bg-orange-400 disabled:cursor-wait disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
              {running ? "正在汇总 Vibe 数据…" : "生成专业研究日报"}
            </button>
            <button
              type="button"
              onClick={() => { void askVibe(); }}
              disabled={!report || agentRunning}
              className="inline-flex items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Bot className="h-4 w-4" />
              {agentRunning ? "正在启动…" : "交给 Vibe 深度研判"}
            </button>
            <button
              type="button"
              onClick={() => { void notify(); }}
              disabled={
                !report
                || notificationRunning
                || !capability?.delivery?.enabled
                || (capability.delivery.configured_channels.length === 0)
              }
              title={
                capability?.delivery?.enabled
                  ? "发送当日研究简报；同一日期自动去重"
                  : "通知当前关闭；使用启动脚本的 -EnableNotifications 开关启用"
              }
              className="inline-flex items-center gap-2 rounded-xl border border-emerald-300/30 bg-emerald-400/10 px-4 py-2.5 text-sm font-semibold text-emerald-100 backdrop-blur transition hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Bell className={`h-4 w-4 ${notificationRunning ? "animate-pulse" : ""}`} />
              {notificationRunning ? "正在发送…" : "发送研究通知"}
            </button>
          </div>
        </div>
        <div className="relative mt-6 flex flex-wrap gap-2">
          {(capability?.capabilities ?? [
            "行情与多源降级", "历史价格位置", "财务估值", "融资融券", "新闻证据", "风格代理",
          ]).map((item) => (
            <span key={item} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
              {item}
            </span>
          ))}
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-5 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 sm:mx-7">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div><p className="font-semibold">研究报告暂不可用</p><p className="mt-1">{error}</p></div>
        </div>
      )}

      {!report ? (
        <div className="grid min-h-64 place-items-center p-8 text-center">
          <div>
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-orange-100 text-orange-600">
              <BarChart3 className="h-7 w-7" />
            </div>
            <p className="mt-4 text-lg font-semibold text-slate-900">尚无专业研究日报</p>
            <p className="mt-1 text-sm text-slate-500">点击上方按钮，系统将调用真实 Vibe 数据，不使用样例替代。</p>
          </div>
        </div>
      ) : (
        <div className="space-y-6 p-5 sm:p-7">
          <div className="rounded-2xl border border-orange-200 bg-gradient-to-r from-orange-50 to-amber-50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-orange-700">Chief Research View</p>
                <p className="mt-2 text-base font-semibold leading-7 text-slate-900">{report.conclusion}</p>
              </div>
              <div className="rounded-xl bg-white px-3 py-2 text-right shadow-sm">
                <p className="text-xs text-slate-500">数据截止</p>
                <p className="font-mono text-sm font-semibold text-slate-800">{report.report_date}</p>
              </div>
            </div>
          </div>

          {shadow && (
            <div className="rounded-2xl border border-indigo-200 bg-gradient-to-r from-indigo-950 to-slate-900 p-5 text-white shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-300">
                    Shadow Portfolio · T+20
                  </p>
                  <h3 className="mt-2 text-xl font-bold">影子账户收益跟踪</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-300">
                    盘后只生成研究意图，下一交易日数据才记模拟成交；不会调用真实订单。
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <div className="rounded-xl bg-white/10 px-3 py-2">
                    <p className="text-[10px] text-slate-300">初始资金</p>
                    <p className="font-bold">¥{shadow.initial_cash.toLocaleString()}</p>
                  </div>
                  <div className="rounded-xl bg-white/10 px-3 py-2">
                    <p className="text-[10px] text-slate-300">当前权益</p>
                    <p className="font-bold">¥{(shadowLatest?.equity ?? shadow.initial_cash).toLocaleString()}</p>
                  </div>
                  <div className="rounded-xl bg-white/10 px-3 py-2">
                    <p className="text-[10px] text-slate-300">累计收益</p>
                    <p className={`font-bold ${(shadowLatest?.total_return_pct ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                      {signedPercent(shadowLatest?.total_return_pct ?? 0)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-white/10 px-3 py-2">
                    <p className="text-[10px] text-slate-300">持仓 / 待成交</p>
                    <p className="font-bold">{shadow.open_positions.length} / {shadow.pending_intents.length}</p>
                  </div>
                </div>
              </div>
              {shadow.open_positions.length > 0 && (
                <div className="mt-4 grid gap-2 md:grid-cols-2">
                  {shadow.open_positions.map((position) => (
                    <div key={position.position_id} className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-semibold">
                          {position.name} <span className="font-mono text-xs text-slate-300">{position.symbol}</span>
                        </p>
                        <p className={position.return_pct >= 0 ? "text-emerald-300" : "text-rose-300"}>
                          {signedPercent(position.return_pct)}
                        </p>
                      </div>
                      <p className="mt-1 text-xs text-slate-300">
                        模拟成本 {position.entry_price} · T+{position.observed_sessions}/{position.horizon} · 盈亏 ¥{position.pnl.toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm">
            <div>
              <p className="font-semibold text-emerald-950">日报通知</p>
              <p className="mt-0.5 text-xs text-emerald-800">
                {capability?.delivery?.enabled
                  ? `${capability.delivery.scheduler_enabled ? "每日盘后自动发送" : "手工确认发送"} · 已配置 ${capability.delivery.configured_channels.join(" + ") || "0 个渠道"} · 24小时同因去重`
                  : "默认关闭；启动时加入 -EnableNotifications 后，可发送到已配置渠道。"}
              </p>
            </div>
            {notificationMessage && (
              <p className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-emerald-800 shadow-sm">
                {notificationMessage}
              </p>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <MetricTile
              label="市场状态"
              value={report.market.regime ?? (report.market.panic ? "恐慌/系统性回撤" : "待更新")}
              detail={report.market.panic ? "已触发系统性恐慌规则" : "未触发系统性恐慌规则"}
              tone={report.market.panic ? "text-rose-600" : "text-emerald-600"}
            />
            <MetricTile
              label="上证 20 日"
              value={signedPercent(report.market.shanghai_20d_return_pct)}
              detail={`60日点位变化 ${report.market.shanghai_60d_point_change?.toFixed(2) ?? "—"} 点`}
              tone={valueTone(report.market.shanghai_20d_return_pct)}
            />
            <MetricTile
              label="全市场跌停"
              value={report.market.limit_down_count === null ? "—" : `${report.market.limit_down_count} 家`}
              detail={report.market.limit_down_count_quality === "official_pool" ? "官方当日跌停池" : "数据待核验"}
              tone={(report.market.limit_down_count ?? 0) >= 1000 ? "text-rose-600" : "text-slate-950"}
            />
            <MetricTile
              label="银行 - 科技（20日）"
              value={signedPercent(style.bank_minus_technology_20d_pct)}
              detail="银行ETF相对科创50ETF"
              tone={valueTone(style.bank_minus_technology_20d_pct)}
            />
            <MetricTile
              label="研究标的"
              value={`${report.assets.length} 个`}
              detail="中天科技 / 科创50ETF"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <Landmark className="h-5 w-5 text-blue-600" />
                <h3 className="font-semibold text-slate-900">大盘与风格联动</h3>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">银行ETF 20日</p>
                  <p className={`mt-1 text-lg font-bold ${valueTone(style.bank_20d_return_pct)}`}>
                    {signedPercent(style.bank_20d_return_pct)}
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">科创50ETF 20日</p>
                  <p className={`mt-1 text-lg font-bold ${valueTone(style.technology_20d_return_pct)}`}>
                    {signedPercent(style.technology_20d_return_pct)}
                  </p>
                </div>
              </div>
              <p className="mt-4 text-sm font-medium text-slate-800">{style.interpretation}</p>
              <p className="mt-2 rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs leading-5 text-blue-800">
                {style.state_support_inference}
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-orange-600" />
                <h3 className="font-semibold text-slate-900">恐慌规则</h3>
              </div>
              <div className="mt-4 space-y-2 text-sm">
                {[
                  ["个股60日 ≤ -30%", report.assets.some((item) => item.return_60d_pct !== null && item.return_60d_pct <= -30)],
                  ["上证60日 ≤ -200点", (report.market.shanghai_60d_point_change ?? 0) <= -200],
                  ["当日跌停 ≥ 1000家", (report.market.limit_down_count ?? 0) >= 1000],
                ].map(([label, active]) => (
                  <div key={String(label)} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                    <span>{String(label)}</span>
                    {active
                      ? <CheckCircle2 className="h-4 w-4 text-rose-500" />
                      : <CircleDashed className="h-4 w-4 text-slate-400" />}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Vibe Full Research</p>
                <h3 className="mt-1 font-bold text-slate-950">全面研判流水线</h3>
              </div>
              <p className="text-xs text-slate-500">按标的适用性调用，不机械堆叠无关模型</p>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {report.research_workflow?.stages.map((stage, index) => (
                <div key={stage.name} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-slate-900">{index + 1}. {stage.name}</p>
                    <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${
                      stage.status === "ready" || stage.status === "eligible"
                        ? "bg-emerald-100 text-emerald-700"
                        : stage.status === "gated"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-blue-100 text-blue-700"
                    }`}>
                      {stage.status === "ready" ? "已纳入日报"
                        : stage.status === "eligible" ? "可启动影子验证"
                          : stage.status === "gated" ? "等待行动门槛"
                            : "点击深度研判后运行"}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-600">{stage.capabilities.join(" · ")}</p>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Watchlist Research</p>
                <h3 className="mt-1 text-xl font-bold text-slate-950">自选标的深度拆解</h3>
              </div>
              <div className="flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
                {report.assets.map((asset) => (
                  <button
                    key={asset.symbol}
                    type="button"
                    onClick={() => setSelectedSymbol(asset.symbol)}
                    className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                      selected?.symbol === asset.symbol
                        ? "bg-slate-900 text-white shadow-sm"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    <span className="flex flex-col items-start">
                      <span>{asset.name}</span>
                      <span className={`text-[10px] ${selected?.symbol === asset.symbol ? "text-slate-300" : "text-slate-400"}`}>
                        {asset.action_label}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {selected && (
              <article className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-100 bg-gradient-to-r from-white to-slate-50 p-5 sm:p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-2xl font-bold text-slate-950">{selected.name}</h4>
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 font-mono text-xs text-slate-600">{selected.symbol}</span>
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${ACTION_STYLES[selected.action_level]}`}>
                          {selected.action_label}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-slate-500">
                        最新交易日 {selected.effective_trade_date ?? "—"} · 数据源 {selected.data_source}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-500">最新收盘</p>
                      <p className="text-3xl font-bold tracking-tight text-slate-950">{selected.latest_close ?? "—"}</p>
                    </div>
                  </div>
                  <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                      ["5日", selected.return_5d_pct],
                      ["20日", selected.return_20d_pct],
                      ["60日", selected.return_60d_pct],
                      ["相对上证20日", selected.relative_to_shanghai_20d_pct],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-3">
                        <p className="text-xs text-slate-500">{String(label)}</p>
                        <p className={`mt-1 text-lg font-bold ${valueTone(value as number | null)}`}>
                          {signedPercent(value as number | null)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid gap-5 p-5 sm:p-6 xl:grid-cols-2">
                  <section className="rounded-2xl border border-slate-200 p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Target className="h-5 w-5 text-orange-600" />
                        <h5 className="font-bold text-slate-900">什么时候值得开始行动？</h5>
                      </div>
                      <span className="rounded-full bg-orange-100 px-3 py-1 text-xs font-bold text-orange-800">
                        {selected.entry_framework.label}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-600">{selected.entry_framework.summary}</p>
                    {selected.entry_framework.reference_zones.length > 0 && (
                      <div className="mt-4 grid gap-2 sm:grid-cols-2">
                        {selected.entry_framework.reference_zones.map((zone) => (
                          <div key={zone.name} className="rounded-xl bg-orange-50 p-3">
                            <p className="text-xs font-semibold text-orange-800">{zone.name}</p>
                            <p className="mt-1 text-lg font-bold text-slate-900">{zone.low} – {zone.high}</p>
                            <p className="mt-1 text-xs text-slate-500">{zone.basis}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="mt-4 grid gap-4 sm:grid-cols-2">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">已经满足</p>
                        <ul className="mt-2 space-y-2 text-sm text-slate-700">
                          {selected.entry_framework.reasons.length === 0 && <li>暂无关键确认信号</li>}
                          {selected.entry_framework.reasons.map((item) => (
                            <li key={item} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />{item}</li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">仍需等待</p>
                        <ul className="mt-2 space-y-2 text-sm text-slate-700">
                          {selected.entry_framework.conditions.map((item) => (
                            <li key={item} className="flex gap-2"><CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />{item}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </section>

                  {selected.formal_research && (
                    <section className="rounded-2xl border border-indigo-200 bg-indigo-50/40 p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <ShieldCheck className="h-5 w-5 text-indigo-600" />
                            <h5 className="font-bold text-slate-900">正式研究门禁</h5>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-slate-600">
                            行动等级由 {selected.formal_research.decision_source} 统一生成，
                            日报本身不再单独判断买点。
                          </p>
                        </div>
                        <span className="rounded-full border border-indigo-200 bg-white px-3 py-1 text-xs font-bold text-indigo-700">
                          {selected.formal_research.opportunity_status} / {selected.formal_research.research_priority}
                        </span>
                      </div>
                      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <MetricTile
                          label="Thesis"
                          value={`${selected.formal_research.thesis_status} · ${
                            selected.formal_research.thesis_initialized ? "已审核初始化" : "草稿"
                          }`}
                        />
                        <MetricTile label="归因" value={selected.formal_research.attribution_scope} />
                        <MetricTile label="永久性" value={selected.formal_research.permanence} />
                        <MetricTile label="估值状态" value={selected.formal_research.valuation_status} />
                      </div>
                      <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">
                          尚未通过的门禁
                        </p>
                        {selected.formal_research.blocked_reasons.length === 0 ? (
                          <p className="mt-2 text-sm text-emerald-700">所有正式研究门禁已通过。</p>
                        ) : (
                          <ul className="mt-2 space-y-1 text-sm text-amber-900">
                            {selected.formal_research.blocked_reasons.map((reason) => (
                              <li key={reason}>• {reason}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                      <p className="mt-3 text-xs leading-5 text-slate-500">
                        首要否定问题：{selected.formal_research.first_rejection_question}
                      </p>
                      <div className="mt-4 grid gap-3 lg:grid-cols-2">
                        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                            已审核支持证据
                          </p>
                          {selected.formal_research.supporting_evidence.length === 0 ? (
                            <p className="mt-2 text-sm text-emerald-900">暂无正式支持证据。</p>
                          ) : (
                            <ul className="mt-2 space-y-2 text-sm text-emerald-950">
                              {selected.formal_research.supporting_evidence.map((item) => (
                                <li key={item.evidence_id}>
                                  <span className="font-semibold">{item.title}</span>
                                  <span className="block text-xs text-emerald-800">
                                    {item.provider} · {item.available_at.slice(0, 10)}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-rose-800">
                            已审核反方证据
                          </p>
                          {selected.formal_research.counter_evidence.length === 0 ? (
                            <p className="mt-2 text-sm text-rose-900">暂无正式反方证据。</p>
                          ) : (
                            <ul className="mt-2 space-y-2 text-sm text-rose-950">
                              {selected.formal_research.counter_evidence.map((item) => (
                                <li key={item.evidence_id}>
                                  <span className="font-semibold">{item.title}</span>
                                  <span className="block text-xs text-rose-800">
                                    {item.provider} · {item.available_at.slice(0, 10)}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    </section>
                  )}

                  <section className="rounded-2xl border border-slate-200 p-5">
                    <div className="flex items-center gap-2">
                      <Activity className="h-5 w-5 text-blue-600" />
                      <h5 className="font-bold text-slate-900">技术面与历史位置</h5>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                      <MetricTile label="趋势" value={selected.technical.trend} />
                      <MetricTile label="RSI 14" value={selected.technical.rsi14?.toFixed(1) ?? "—"} />
                      <MetricTile label="MA20" value={selected.technical.ma20?.toFixed(2) ?? "—"} />
                      <MetricTile label="MA60" value={selected.technical.ma60?.toFixed(2) ?? "—"} />
                      <MetricTile
                        label="距近一年高点"
                        value={signedPercent(selected.history_position.drawdown_from_high_pct)}
                        tone="text-rose-600"
                      />
                      <MetricTile
                        label="近一年价格分位"
                        value={selected.history_position.price_percentile === null ? "—" : `${selected.history_position.price_percentile.toFixed(1)}%`}
                      />
                    </div>
                    <div className="mt-4 flex items-center gap-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                      {selected.technical.stabilization
                        ? <TrendingUp className="h-5 w-5 text-emerald-600" />
                        : <TrendingDown className="h-5 w-5 text-rose-600" />}
                      {selected.technical.stabilization
                        ? "已出现初步止跌：站上MA20且5日收益转正"
                        : "尚未确认止跌：价格趋势仍需观察"}
                    </div>
                  </section>

                  <section className="rounded-2xl border border-slate-200 p-5">
                    <div className="flex items-center gap-2">
                      <Gauge className="h-5 w-5 text-violet-600" />
                      <h5 className="font-bold text-slate-900">估值与基本面</h5>
                    </div>
                    {selected.valuation.available ? (
                      <>
                        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                          <MetricTile label="静态PE" value={`${selected.valuation.current_pe?.toFixed(1)}x`} />
                          <MetricTile label="ROE" value={signedPercent(selected.fundamentals?.roe_pct ?? null)} />
                          <MetricTile label="毛利率" value={signedPercent(selected.fundamentals?.gross_margin_pct ?? null)} />
                          <MetricTile label="净利增速" value={signedPercent(selected.fundamentals?.net_profit_yoy_pct ?? null)} />
                        </div>
                        <div className="mt-4 rounded-xl bg-violet-50 p-4 text-sm">
                          <p className="font-semibold text-violet-900">{selected.valuation.assessment}</p>
                          <p className="mt-1 text-violet-800">{selected.valuation.method}</p>
                          <p className="mt-1 text-xs text-violet-700">财务期：{selected.valuation.eps_period ?? "—"}，需结合下一期利润质量复核。</p>
                        </div>
                      </>
                    ) : (
                      <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
                        {selected.valuation.method}
                      </div>
                    )}
                  </section>

                  <section className="rounded-2xl border border-slate-200 p-5">
                    <div className="flex items-center gap-2">
                      <WalletCards className="h-5 w-5 text-cyan-600" />
                      <h5 className="font-bold text-slate-900">资金与杠杆</h5>
                    </div>
                    {selected.margin || selected.fund_flow ? (
                      <div className="mt-4 space-y-3">
                        {selected.margin && (
                          <div className="rounded-xl bg-slate-50 p-4">
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-sm text-slate-600">融资余额</span>
                              <span className="font-bold text-slate-900">{compactMoney(selected.margin.financing_balance_cny)}</span>
                            </div>
                            <div className="mt-2 flex items-center justify-between gap-3">
                              <span className="text-sm text-slate-600">{selected.margin.period_days}日变化</span>
                              <span className={`font-bold ${valueTone(selected.margin.period_change_pct)}`}>
                                {signedPercent(selected.margin.period_change_pct)}
                              </span>
                            </div>
                            <p className="mt-3 text-xs leading-5 text-slate-500">{selected.margin.interpretation}</p>
                          </div>
                        )}
                        {selected.fund_flow && (
                          <div className="grid grid-cols-2 gap-3">
                            <MetricTile label="主力净流入 5日" value={compactMoney(selected.fund_flow.main_net_inflow_5d_cny)} />
                            <MetricTile label="主力净流入 20日" value={compactMoney(selected.fund_flow.main_net_inflow_20d_cny)} />
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">该标的暂无可靠资金数据，不用空值推导资金结论。</p>
                    )}
                  </section>
                </div>

                <div className="grid gap-5 border-t border-slate-100 p-5 sm:p-6 lg:grid-cols-[0.7fr_1.3fr]">
                  <section>
                    <div className="flex items-center gap-2">
                      <BarChart3 className="h-5 w-5 text-indigo-600" />
                      <h5 className="font-bold text-slate-900">行业与概念暴露</h5>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selected.sectors.length === 0 && <span className="text-sm text-slate-500">暂无行业数据</span>}
                      {selected.sectors.map((sector) => (
                        <span key={sector.code ?? sector.name} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-700">
                          {sector.name}
                          {sector.change_pct !== null && <span className={`ml-1 ${valueTone(sector.change_pct)}`}>{signedPercent(sector.change_pct)}</span>}
                        </span>
                      ))}
                    </div>
                  </section>
                  <section>
                    <div className="flex items-center gap-2">
                      <Newspaper className="h-5 w-5 text-orange-600" />
                      <h5 className="font-bold text-slate-900">最新消息证据</h5>
                    </div>
                    <div className="mt-3 space-y-2">
                      {selected.news.length === 0 && <p className="text-sm text-slate-500">暂无可验证新闻，不以传闻补位。</p>}
                      {selected.news.slice(0, 5).map((article) => (
                        <a
                          key={`${article.published}-${article.title}`}
                          href={article.url ?? undefined}
                          target="_blank"
                          rel="noreferrer"
                          className="group flex items-start justify-between gap-4 rounded-xl border border-slate-200 p-3 transition hover:border-orange-200 hover:bg-orange-50"
                        >
                          <div>
                            <p className="text-sm font-medium text-slate-800 group-hover:text-orange-800">{article.title}</p>
                            <p className="mt-1 text-xs text-slate-500">{article.source ?? "公开来源"} · {article.published ?? "时间未知"}</p>
                          </div>
                          <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 group-hover:text-orange-600" />
                        </a>
                      ))}
                    </div>
                  </section>
                </div>
              </article>
            )}
          </div>

          {report.data_gaps.length > 0 && (
            <details className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
              <summary className="cursor-pointer font-semibold text-amber-900">数据缺口与核验说明（{report.data_gaps.length}）</summary>
              <ul className="mt-3 list-inside list-disc space-y-1 text-amber-800">
                {report.data_gaps.map((gap) => <li key={gap}>{gap}</li>)}
              </ul>
            </details>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-900 px-4 py-3 text-xs text-slate-300">
            <span>Research Candidate，不是交易指令。所有区间均需结合新财报、消息与价格确认。</span>
            <span className="flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" />只读 · 不通知 · 不调度 · 不交易</span>
          </div>
        </div>
      )}
    </section>
  );
}

function ThesisCard({ thesis, readiness }: {
  thesis: InvestmentResearchThesis;
  readiness?: InvestmentResearchEvidenceReadiness;
}) {
  const version = thesis.current_version;
  return (
    <article className="rounded-xl border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{thesis.name}</h3>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
              {SCOPE_LABELS[thesis.scope]}
            </span>
          </div>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{thesis.thesis_id}</p>
        </div>
        {version ? (
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/5 px-2 py-1 text-xs text-emerald-700">
            {version.status} · v{version.version_number}
          </span>
        ) : (
          <span className="flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-xs text-amber-700">
            <CircleDashed className="h-3 w-3" /> 等待证据初始化
          </span>
        )}
      </div>
      {!version && readiness && (
        <div className="mt-4 space-y-2 text-sm">
          <p className="font-medium">证据就绪度：{READINESS_LABELS[readiness.verdict]}</p>
          <p className="text-muted-foreground">{readiness.first_rejection_question}</p>
          <p className="text-xs text-muted-foreground">
            支持 {readiness.supporting_association_ids.length} · 反方 {readiness.counter_association_ids.length} ·
            质量警告 {readiness.quality_warnings.length}
          </p>
        </div>
      )}
      {version ? (
        <div className="mt-4 space-y-3 text-sm">
          <p>{version.core_claim}</p>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded-md bg-muted/60 p-2"><p className="text-muted-foreground">支持证据</p><p className="font-semibold">{version.supporting_evidence_ids.length}</p></div>
            <div className="rounded-md bg-muted/60 p-2"><p className="text-muted-foreground">反方证据</p><p className="font-semibold">{version.counter_evidence_ids.length}</p></div>
            <div className="rounded-md bg-muted/60 p-2"><p className="text-muted-foreground">下次复核</p><p className="font-semibold">{new Date(version.next_review_at).toLocaleDateString()}</p></div>
          </div>
          <p className="text-xs text-muted-foreground">最近变化：{version.change_summary}</p>
        </div>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">
          当前只是研究蓝图。完成可追溯的支持证据、反方证据、催化剂、失效条件和审批后，才会形成首个 Thesis Version。
        </p>
      )}
    </article>
  );
}

function DailyPanel({ report }: { report: InvestmentResearchDailyReport | null }) {
  if (!report) {
    return (
      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">今日研究日报</h2>
        <p className="mt-2 text-sm text-muted-foreground">今日完整日报尚未生成。系统不会用旧数据伪装成今天的结论。</p>
      </section>
    );
  }
  return (
    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">今日研究日报 · {report.trade_date}</h2>
        <span className="rounded-full bg-muted px-2 py-1 text-xs">{report.market_state?.regime ?? "市场数据不可用"}</span>
      </div>
      <p className="rounded-md bg-muted/60 p-3 text-sm">{report.conclusion}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="flex items-center gap-1 text-sm font-semibold"><Search className="h-4 w-4" /> Discovery Leads</h3>
          <div className="mt-2 space-y-2">
            {report.discovery_leads.length === 0 && <p className="text-sm text-muted-foreground">暂无新的研究线索。</p>}
            {report.discovery_leads.map((lead) => (
              <article key={lead.lead_id} className="rounded-md border p-3 text-sm">
                <div className="flex items-center justify-between gap-2"><span className="font-mono">{lead.asset_id}</span><span className="text-xs text-muted-foreground">{DISPOSITION_LABELS[lead.disposition]}</span></div>
                <p className="mt-2 text-xs">首要否定问题：{lead.first_rejection_question}</p>
              </article>
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-sm font-semibold">Research Candidates</h3>
          <div className="mt-2 space-y-2">
            {report.candidates.length === 0 && <p className="text-sm text-muted-foreground">暂无达到正式候选标准的机会。</p>}
            {report.candidates.map((candidate) => (
              <article key={candidate.candidate_id} className="rounded-md border p-3 text-sm">
                <div className="flex items-center justify-between gap-2"><span className="font-mono">{candidate.asset_id}</span><span className="text-xs">{candidate.action_level}</span></div>
                <p className="mt-2 text-xs">首要否定问题：{candidate.first_rejection_question}</p>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function EvidenceInbox({ items }: { items: InvestmentResearchEvidenceInboxItem[] }) {
  return (
    <section className="rounded-xl border bg-card p-5">
      <div className="flex items-center gap-2"><FileCheck2 className="h-5 w-5 text-primary" /><h2 className="font-semibold">待审证据入口</h2></div>
      <p className="mt-1 text-sm text-muted-foreground">自动采集内容默认不参与 Thesis；只有人工审核通过后才具备研究资格。</p>
      <div className="mt-3 space-y-2">
        {items.length === 0 && <p className="rounded-md bg-muted/60 p-3 text-sm">当前没有待审证据。</p>}
        {items.slice(0, 5).map((item) => (
          <article key={item.inbox_item_id} className="rounded-md border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{item.title}</span><span className="text-xs text-muted-foreground">{item.provider} · {item.proposed_direction}</span></div>
            <p className="mt-1 text-xs text-muted-foreground">拟关联：{item.proposed_subject_type}/{item.proposed_subject_id}</p>
            <p className="mt-2">{item.summary}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function AcceptedEvidence({ items }: { items: InvestmentResearchEvidenceInboxItem[] }) {
  return (
    <section className="rounded-xl border bg-card p-5">
      <h2 className="font-semibold">已审核上下文证据</h2>
      <p className="mt-1 text-sm text-muted-foreground">方向属于具体 Thesis／Opportunity，不再被当作来源文件的全局属性。</p>
      <div className="mt-3 space-y-2">
        {items.length === 0 && <p className="rounded-md bg-muted/60 p-3 text-sm">当前没有已接受证据。</p>}
        {items.slice(0, 5).map((item) => (
          <article key={item.inbox_item_id} className="rounded-md border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{item.title}</span>
              <span className="text-xs text-muted-foreground">{item.review?.final_direction ?? "unclassified"}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              关联：{item.review?.final_subject_type}/{item.review?.final_subject_id} · 审核人 {item.review?.reviewer}
            </p>
            <p className="mt-2">{item.review?.rationale}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function formatPercent(value: number | null): string {
  return value === null ? "无数据" : `${(value * 100).toFixed(2)}%`;
}

function HistoricalOutcomeSection({
  report,
  running,
  error,
  onAutomatic,
  onImport,
}: {
  report: HistoricalEvaluationReport | null;
  running: boolean;
  error: string;
  onAutomatic: (stockCode: string, evaluationDate: string) => void;
  onImport: (file: File) => void;
}) {
  const [stockCode, setStockCode] = useState("000001");
  const [evaluationDate, setEvaluationDate] = useState("");
  const latestEvaluationDate = latestPossibleT20Date();
  const t20 = report?.horizons.find((item) => item.horizon === 20) ?? null;
  const automaticReady = /^\d{6}$/.test(stockCode)
    && Boolean(evaluationDate)
    && evaluationDate <= latestEvaluationDate;
  return (
    <section className="rounded-xl border bg-card p-5">
      <div>
        <div>
          <h2 className="font-semibold">历史 T+20 结果评测</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            输入股票代码和历史评估日期，系统自动获取个股前复权行情与沪深300同期行情。
          </p>
        </div>
        <div className="mt-3 grid gap-3 rounded-md border bg-muted/20 p-3 sm:grid-cols-3">
          <label className="text-xs font-medium">
            股票代码
            <input
              aria-label="历史评测股票代码"
              value={stockCode}
              inputMode="numeric"
              maxLength={6}
              disabled={running}
              onChange={(event) => setStockCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              className="mt-1 w-full rounded-md border bg-background px-2 py-2"
              placeholder="例如 000001"
            />
          </label>
          <label className="text-xs font-medium">
            历史评估日期
            <input
              aria-label="历史评估日期"
              type="date"
              value={evaluationDate}
              max={latestEvaluationDate}
              disabled={running}
              onChange={(event) => setEvaluationDate(event.target.value)}
              className="mt-1 w-full rounded-md border bg-background px-2 py-2"
            />
          </label>
          <div className="flex items-end">
            <button
              type="button"
              disabled={running || !automaticReady}
              onClick={() => onAutomatic(stockCode, evaluationDate)}
              className="w-full rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
            >
              {running ? "正在自动获取…" : "自动获取并评测 T+20"}
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          最晚可选 {latestEvaluationDate}（按20个工作日估算）；遇交易所休市时可能需要选择更早日期。
        </p>
        <details className="mt-3 rounded-md border p-3 text-xs">
          <summary className="cursor-pointer font-medium">
            自动获取失败 / 高级选项：手工 JSON 导入
          </summary>
          <p className="mt-2 text-muted-foreground">
            仅在数据源权限、网络、限频或日期覆盖不足时使用。手工数据仍通过同一套校验和收益计算逻辑。
          </p>
          <label className={`mt-2 inline-block rounded-md border px-3 py-2 font-medium ${running ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}>
            导入历史价格 JSON
            <input
              type="file"
              accept=".json,application/json"
              disabled={running}
              className="sr-only"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                if (file) onImport(file);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </details>
      </div>
      {error && (
        <p className="mt-3 whitespace-pre-line rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
          {error}
        </p>
      )}
      {!report && !error && (
        <p className="mt-3 text-sm text-muted-foreground">
          请选择已经走完 T+20 交易日的历史日期。系统不会用样例数据代替真实获取结果。
        </p>
      )}
      {report && (
        <div className="mt-3 space-y-3">
          <div className="grid gap-2 rounded-md border p-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <div><p className="text-muted-foreground">标的</p><p className="font-medium">{report.stock_code}</p></div>
            <div>
              <p className="text-muted-foreground">请求日 → 实际评估交易日 / 入场价</p>
              <p className="font-medium">
                {report.requested_evaluation_date ?? report.evaluation_date}
                {" → "}
                {report.effective_evaluation_date ?? report.evaluation_date}
                {" / "}
                {report.entry_price}
              </p>
            </div>
            <div><p className="text-muted-foreground">数据范围</p><p className="font-medium">{report.coverage ? `${report.coverage.first_trade_date} 至 ${report.coverage.last_trade_date}` : "未提供"}</p></div>
            <div><p className="text-muted-foreground">来源 / 复权</p><p className="font-medium">{report.input_mode} / {report.adjustment}</p></div>
            <div className="sm:col-span-2"><p className="text-muted-foreground">组件来源</p><p className="font-medium">{Object.entries(report.component_sources ?? {}).map(([component, source]) => `${component}: ${source}`).join("；") || report.data_source}</p></div>
            <div className="sm:col-span-2"><p className="text-muted-foreground">能力状态</p><p className="font-medium">{report.verification_status} / {report.capability}</p></div>
          </div>
          {t20 && (
            <div className="grid gap-2 rounded-md bg-muted/50 p-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
              <div><p className="text-muted-foreground">T+20交易日</p><p className="font-semibold">{t20.target_trading_date ?? "覆盖不足"}</p></div>
              <div><p className="text-muted-foreground">资产收益</p><p className="font-semibold">{formatPercent(t20.asset_return)}</p></div>
              <div><p className="text-muted-foreground">沪深300 / 超额</p><p className="font-semibold">{formatPercent(t20.benchmark_return)} / {formatPercent(t20.excess_return)}</p></div>
              <div><p className="text-muted-foreground">最大回撤</p><p className="font-semibold">{formatPercent(t20.maximum_drawdown)}</p></div>
              {t20.data_gap && <p className="text-amber-700 sm:col-span-2 lg:col-span-4">数据缺口：{t20.data_gap}</p>}
            </div>
          )}
          {report.warnings.map((warning) => (
            <p key={warning} className="text-xs text-amber-700">{warning}</p>
          ))}
        </div>
      )}
    </section>
  );
}

function PanicShadowSection({
  status,
  running,
  dateMode,
  selectedDate,
  onDateModeChange,
  onSelectedDateChange,
  onRun,
  onManualImport,
}: {
  status: PanicResearchViewState;
  running: boolean;
  dateMode: PanicShadowDateMode;
  selectedDate: string;
  onDateModeChange: (value: PanicShadowDateMode) => void;
  onSelectedDateChange: (value: string) => void;
  onRun: () => void;
  onManualImport: (file: File) => void;
}) {
  const actionLabel = dateMode === "auto"
    ? "生成最近交易日盘后报告"
    : "回放所选日期";
  const runButton = (
    <button
      type="button"
      onClick={onRun}
      disabled={running}
      className="rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
    >
      {running ? "正在获取全市场数据（最长约45秒）…" : actionLabel}
    </button>
  );
  const actions = (
    <div className="flex flex-wrap gap-2">
      {runButton}
      <label className={`rounded-md border px-3 py-2 text-xs font-medium ${running ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}>
        导入对应日期 JSON
        <input
          type="file"
          accept=".json,application/json"
          disabled={running}
          className="sr-only"
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            if (file) onManualImport(file);
            event.currentTarget.value = "";
          }}
        />
      </label>
    </div>
  );
  const dateControls = (
    <div className="mb-3 grid gap-3 rounded-md border bg-muted/30 p-3 sm:grid-cols-2">
      <label className="text-xs font-medium">
        日期模式
        <select
          value={dateMode}
          disabled={running}
          onChange={(event) => onDateModeChange(event.target.value as PanicShadowDateMode)}
          className="mt-1 w-full rounded-md border bg-background px-2 py-2"
        >
          <option value="auto">自动：最近完整交易日</option>
          <option value="selected">指定日期</option>
        </select>
      </label>
      <label className="text-xs font-medium">
        分析日期
        <input
          type="date"
          value={selectedDate}
          max={shanghaiDate()}
          disabled={running || dateMode !== "selected"}
          onChange={(event) => onSelectedDateChange(event.target.value)}
          className="mt-1 w-full rounded-md border bg-background px-2 py-2 disabled:opacity-60"
        />
      </label>
    </div>
  );
  if (status.kind === "disabled") {
    return (
      <section className="rounded-xl border border-dashed bg-card p-5">
        <h2 className="font-semibold">A股盘后恐慌初筛</h2>
        <p className="mt-2 text-sm text-muted-foreground">影子报告功能未启用。该功能需要后端同时启用投资研究和影子报告 API。</p>
      </section>
    );
  }
  if (status.kind === "loading") {
    return (
      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">A股盘后恐慌初筛</h2>
        <p className="mt-2 text-sm text-muted-foreground">正在读取影子报告状态…</p>
      </section>
    );
  }
  if (status.kind === "error") {
    const label = {
      authentication: "认证失败",
      not_found: "尚无盘后报告",
      invalid_contract: "响应异常",
      data_not_ready: "盘后数据尚未完成",
      historical_data_unavailable: "历史数据不可用",
      provider_unavailable: "Provider不可用",
      invalid_manual_import: "导入文件无效",
      unavailable: "服务不可用",
    }[status.errorKind];
    const description = status.errorKind === "not_found"
      ? "当前还没有已保存的可信报告，可以在收盘后手动生成。"
      : status.errorKind === "authentication"
        ? "请先在设置中填写正确的 Server API key。"
        : status.errorKind === "invalid_contract"
          ? "导入文件或后端报告不符合当前数据契约。"
          : "盘后报告服务暂时没有返回可用结果。";
    return (
      <section className="rounded-xl border border-destructive/40 bg-destructive/5 p-5">
        {dateControls}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">A股盘后恐慌初筛</h2>
            <p className="mt-2 text-sm text-destructive">{label}：{status.message || description}</p>
            {status.reasons.length > 0 && (
              <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-destructive">
                {status.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            )}
          </div>
          {status.errorKind !== "authentication" && actions}
        </div>
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-amber-500/30 bg-card p-5">
      {dateControls}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">A股盘后恐慌初筛</h2>
          <p className="mt-1 text-xs text-muted-foreground">影子模式 · 仅用于人工复核</p>
        </div>
        {actions}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-md bg-muted/60 p-2 text-xs">
          <p className="text-muted-foreground">市场状态</p>
          <p className="font-semibold">{status.report.market.regime}</p>
        </div>
        <div className="rounded-md bg-muted/60 p-2 text-xs">
          <p className="text-muted-foreground">恐慌观测</p>
          <p className="font-semibold">{status.report.market.panic_observation}</p>
        </div>
        <div className="rounded-md bg-muted/60 p-2 text-xs">
          <p className="text-muted-foreground">上涨/下跌/跌停</p>
          <p className="font-semibold">{status.report.market.advance}/{status.report.market.decline}/{status.report.market.limit_down}</p>
        </div>
        <div className="rounded-md bg-muted/60 p-2 text-xs">
          <p className="text-muted-foreground">需人工复核</p>
          <p className="font-semibold">{status.report.manual_review_required ? "是" : "否"}</p>
        </div>
      </div>
      <div className="mt-3 grid gap-2 rounded-md border p-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div><p className="text-muted-foreground">请求日期</p><p className="font-medium">{status.report.requested_date ?? "自动"}</p></div>
        <div><p className="text-muted-foreground">实际交易日</p><p className="font-medium">{status.report.effective_trade_date}</p></div>
        <div><p className="text-muted-foreground">日期解析</p><p className="font-medium">{status.report.date_resolution}</p></div>
        <div><p className="text-muted-foreground">数据来源</p><p className="font-medium">{status.report.input_mode} / {status.report.data_source}</p></div>
        <div className="sm:col-span-2"><p className="text-muted-foreground">解析原因</p><p>{status.report.date_resolution_reason}</p></div>
        <div className="sm:col-span-2"><p className="text-muted-foreground">信息截止</p><p>{status.report.information_cutoff}</p></div>
      </div>
      {status.report.data_gaps.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-2 text-xs text-amber-700">
          <p className="font-medium">数据缺口</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {status.report.data_gaps.map((gap, i) => <li key={i}>{gap}</li>)}
          </ul>
        </div>
      )}
      {status.report.screened_watchlist.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">观察池扫描（{status.report.screened_watchlist.length} 只）</p>
          <div className="max-h-48 space-y-1 overflow-y-auto">
            {status.report.screened_watchlist.map((item) => (
              <div key={item.symbol} className="flex items-center justify-between rounded-md bg-muted/40 px-2 py-1 text-xs">
                <span className="font-mono">{item.symbol}</span>
                <span>{item.change_pct !== null ? `${(item.change_pct * 100).toFixed(1)}%` : "无数据"}</span>
                <span className="text-muted-foreground">{item.data_gap ?? "正常"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {status.candidates.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">研究候选（{status.candidates.length} 个）</p>
          <div className="space-y-2">
            {status.candidates.map((c) => (
              <article key={c.candidate_id ?? c.symbol} className="rounded-md border p-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold">{c.symbol}</span>
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-primary">{c.action_level ?? "未评估"}</span>
                </div>
                <p className="mt-1 text-muted-foreground">置信度 {c.confidence !== null ? `${(c.confidence * 100).toFixed(0)}%` : "未评估"} · 质量 {c.quality_status} · 估值 {c.valuation_status}</p>
                {c.data_gaps.length > 0 && <p className="mt-0.5 text-amber-600">数据缺口：{c.data_gaps.join("；")}</p>}
              </article>
            ))}
          </div>
        </div>
      )}
      {status.versions.length > 0 && (
        <div className="mt-3 border-t pt-2 text-xs text-muted-foreground">
          <p className="font-medium">版本</p>
          <ul className="mt-0.5 space-y-0.5">
            {status.versions.map((v) => (
              <li key={v.component}>{v.component}：{v.version}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3 border-t pt-2 text-xs text-muted-foreground">
        <p className="font-medium">历史结果：{status.report.outcome_evaluation.status}</p>
        <p className="mt-1">
          {status.report.outcome_evaluation.windows.map((item) => (
            <span key={item.horizon} className="mr-3">
              {item.horizon}日：{item.status}
            </span>
          ))}
        </p>
      </div>
    </section>
  );
}

interface ThesisReviewForm {
  coreClaim: string;
  confidence: string;
  supportProvider: string;
  supportLocator: string;
  supportTitle: string;
  supportSummary: string;
  supportPublishedAt: string;
  counterProvider: string;
  counterLocator: string;
  counterTitle: string;
  counterSummary: string;
  counterPublishedAt: string;
  catalysts: string;
  killCriteria: string;
  nextReviewDays: string;
  reviewer: string;
  rationale: string;
  confirmed: boolean;
}

function reviewFormFor(starter: WatchlistThesisStarter): ThesisReviewForm {
  const publishedAt = localDateTimeValue();
  return {
    coreClaim: starter.proposed_core_claim,
    confidence: "0.60",
    supportProvider: "company_announcement",
    supportLocator: "",
    supportTitle: "",
    supportSummary: "",
    supportPublishedAt: publishedAt,
    counterProvider: "company_announcement",
    counterLocator: "",
    counterTitle: "",
    counterSummary: "",
    counterPublishedAt: publishedAt,
    catalysts: starter.proposed_catalysts.join("\n"),
    killCriteria: starter.proposed_kill_criteria.join("\n"),
    nextReviewDays: "30",
    reviewer: "local-owner",
    rationale: "",
    confirmed: false,
  };
}

function EvidenceReviewFields({
  tone, title, provider, locator, evidenceTitle, summary, publishedAt,
  onProvider, onLocator, onTitle, onSummary, onPublishedAt,
}: {
  tone: "support" | "counter";
  title: string;
  provider: string;
  locator: string;
  evidenceTitle: string;
  summary: string;
  publishedAt: string;
  onProvider: (value: string) => void;
  onLocator: (value: string) => void;
  onTitle: (value: string) => void;
  onSummary: (value: string) => void;
  onPublishedAt: (value: string) => void;
}) {
  return (
    <fieldset className={`rounded-xl border p-4 ${
      tone === "support"
        ? "border-emerald-500/30 bg-emerald-500/5"
        : "border-rose-500/30 bg-rose-500/5"
    }`}>
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      <div className="space-y-3">
        <label className="block text-xs font-medium">来源机构
          <input value={provider} onChange={(event) => onProvider(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-3 py-2 font-normal" />
        </label>
        <label className="block text-xs font-medium">原文URL或来源定位
          <input value={locator} onChange={(event) => onLocator(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-3 py-2 font-normal" />
        </label>
        <label className="block text-xs font-medium">证据标题
          <input value={evidenceTitle} onChange={(event) => onTitle(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-3 py-2 font-normal" />
        </label>
        <label className="block text-xs font-medium">证据摘要
          <textarea value={summary} onChange={(event) => onSummary(event.target.value)} rows={3} className="mt-1 w-full rounded-md border bg-background p-3 font-normal" />
        </label>
        <label className="block text-xs font-medium">公开时间
          <input type="datetime-local" value={publishedAt} onChange={(event) => onPublishedAt(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-3 py-2 font-normal" />
        </label>
      </div>
    </fieldset>
  );
}

function ThesisInitializationPanel({
  status,
  onCompleted,
}: {
  status: WatchlistThesisInitializationStatus | null;
  onCompleted: () => Promise<void>;
}) {
  const [selected, setSelected] = useState<WatchlistThesisStarter | null>(null);
  const [form, setForm] = useState<ThesisReviewForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");

  const openReview = (starter: WatchlistThesisStarter) => {
    setSelected(starter);
    setForm(reviewFormFor(starter));
    setMessage("");
    setFormError("");
  };
  const update = <K extends keyof ThesisReviewForm>(
    field: K,
    value: ThesisReviewForm[K],
  ) => setForm((current) => current ? { ...current, [field]: value } : current);

  const submit = async () => {
    if (!selected || !form) return;
    setSaving(true);
    setMessage("");
    setFormError("");
    const payload: ManualThesisInitializationRequest = {
      thesis_id: selected.thesis_id,
      core_claim: form.coreClaim,
      confidence: Number(form.confidence),
      supporting_evidence: [{
        provider: form.supportProvider,
        source_locator: form.supportLocator,
        title: form.supportTitle,
        summary: form.supportSummary,
        published_at: new Date(form.supportPublishedAt).toISOString(),
      }],
      counter_evidence: [{
        provider: form.counterProvider,
        source_locator: form.counterLocator,
        title: form.counterTitle,
        summary: form.counterSummary,
        published_at: new Date(form.counterPublishedAt).toISOString(),
      }],
      catalysts: nonEmptyLines(form.catalysts),
      kill_criteria: nonEmptyLines(form.killCriteria),
      next_review_days: Number(form.nextReviewDays),
      reviewer: form.reviewer,
      review_rationale: form.rationale,
      confirm: form.confirmed,
    };
    try {
      const result = await api.initializeWatchlistThesis(payload);
      setMessage(result.created
        ? "审核版本已建立。请重新生成每日报告，让正式流水线读取该 Thesis。"
        : "该 Thesis 已经完成初始化，没有覆盖原有版本。");
      await onCompleted();
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Thesis 初始化失败");
    } finally {
      setSaving(false);
    }
  };

  if (!status) return null;
  return (
    <section className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="border-b bg-gradient-to-r from-slate-950 to-slate-800 px-5 py-5 text-white">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-orange-300">Human Review Gate</p>
            <h2 className="mt-1 text-xl font-bold">自选资产 Thesis 审核初始化</h2>
            <p className="mt-2 max-w-3xl text-sm text-slate-300">
              行情和自动分析只提供线索。你确认正反证据、催化剂与失效条件后，
              系统才会建立可审计的首个研究版本。
            </p>
          </div>
          <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs">
            人工批准 · 不通知 · 不交易
          </span>
        </div>
      </div>
      <div className="grid gap-3 p-5 md:grid-cols-2">
        {status.items.map((item) => (
          <article key={item.thesis_id} className={`rounded-xl border p-4 ${
            item.initialized
              ? "border-emerald-500/30 bg-emerald-500/5"
              : "border-amber-500/30 bg-amber-500/5"
          }`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-xs text-muted-foreground">{item.symbol}</p>
                <h3 className="mt-1 font-semibold">{item.name}</h3>
              </div>
              <span className={`rounded-full px-2 py-1 text-xs font-medium ${
                item.initialized ? "bg-emerald-500/15 text-emerald-700" : "bg-amber-500/15 text-amber-700"
              }`}>
                {item.initialized ? "已审核初始化" : "等待人工审核"}
              </span>
            </div>
            <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">{item.proposed_core_claim}</p>
            <button type="button" disabled={item.initialized} onClick={() => openReview(item)}
              className="mt-4 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40">
              {item.initialized ? "版本已锁定" : "审核证据并建立 Version 1"}
            </button>
          </article>
        ))}
      </div>
      {selected && form && (
        <div className="border-t bg-slate-50/70 p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-semibold">{selected.name}</h3>
              <p className="text-xs text-muted-foreground">所有字段都会写入本地审计记录；首个版本建立后不会被这张表单覆盖。</p>
            </div>
            <button type="button" className="text-sm text-muted-foreground hover:text-foreground" onClick={() => setSelected(null)}>收起</button>
          </div>
          <div className="space-y-5">
            <label className="block text-sm font-medium">核心投资逻辑
              <textarea value={form.coreClaim} onChange={(event) => update("coreClaim", event.target.value)} rows={3} className="mt-1 w-full rounded-lg border bg-background p-3 font-normal" />
            </label>
            <div className="grid gap-4 lg:grid-cols-2">
              <EvidenceReviewFields
                tone="support" title="支持证据" provider={form.supportProvider}
                locator={form.supportLocator} evidenceTitle={form.supportTitle}
                summary={form.supportSummary} publishedAt={form.supportPublishedAt}
                onProvider={(value) => update("supportProvider", value)}
                onLocator={(value) => update("supportLocator", value)}
                onTitle={(value) => update("supportTitle", value)}
                onSummary={(value) => update("supportSummary", value)}
                onPublishedAt={(value) => update("supportPublishedAt", value)}
              />
              <EvidenceReviewFields
                tone="counter" title="最强反方证据" provider={form.counterProvider}
                locator={form.counterLocator} evidenceTitle={form.counterTitle}
                summary={form.counterSummary} publishedAt={form.counterPublishedAt}
                onProvider={(value) => update("counterProvider", value)}
                onLocator={(value) => update("counterLocator", value)}
                onTitle={(value) => update("counterTitle", value)}
                onSummary={(value) => update("counterSummary", value)}
                onPublishedAt={(value) => update("counterPublishedAt", value)}
              />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <label className="block text-sm font-medium">催化剂（每行一项）
                <textarea value={form.catalysts} onChange={(event) => update("catalysts", event.target.value)} rows={3} className="mt-1 w-full rounded-lg border bg-background p-3 font-normal" />
              </label>
              <label className="block text-sm font-medium">失效条件（每行一项）
                <textarea value={form.killCriteria} onChange={(event) => update("killCriteria", event.target.value)} rows={3} className="mt-1 w-full rounded-lg border bg-background p-3 font-normal" />
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-sm font-medium">初始置信度
                <input type="number" min="0" max="1" step="0.05" value={form.confidence} onChange={(event) => update("confidence", event.target.value)} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 font-normal" />
              </label>
              <label className="text-sm font-medium">复核周期（天）
                <input type="number" min="1" max="365" value={form.nextReviewDays} onChange={(event) => update("nextReviewDays", event.target.value)} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 font-normal" />
              </label>
              <label className="text-sm font-medium">审核人
                <input value={form.reviewer} onChange={(event) => update("reviewer", event.target.value)} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 font-normal" />
              </label>
            </div>
            <label className="block text-sm font-medium">审核理由
              <textarea value={form.rationale} onChange={(event) => update("rationale", event.target.value)} rows={2} placeholder="说明为什么这些证据足以建立一个可证伪、可复核的初始 Thesis。" className="mt-1 w-full rounded-lg border bg-background p-3 font-normal" />
            </label>
            <label className="flex items-start gap-2 rounded-lg border border-orange-500/30 bg-orange-500/5 p-3 text-sm">
              <input type="checkbox" checked={form.confirmed} onChange={(event) => update("confirmed", event.target.checked)} className="mt-0.5" />
              <span>我已阅读来源、支持证据和最强反方证据，并确认这是研究初始化，不是买入指令。</span>
            </label>
            {formError && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{formError}</div>}
            {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-700">{message}</div>}
            <button type="button" disabled={saving || !form.confirmed} onClick={() => { void submit(); }}
              className="rounded-lg bg-orange-500 px-4 py-2.5 text-sm font-semibold text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-40">
              {saving ? "正在写入审核记录…" : "确认审核并建立 Version 1"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export function InvestmentResearch() {
  const [status, setStatus] = useState<InvestmentResearchStatus | null>(null);
  const [theses, setTheses] = useState<InvestmentResearchThesis[]>([]);
  const [pendingEvidence, setPendingEvidence] = useState<InvestmentResearchEvidenceInboxItem[]>([]);
  const [acceptedEvidence, setAcceptedEvidence] = useState<InvestmentResearchEvidenceInboxItem[]>([]);
  const [readiness, setReadiness] = useState<InvestmentResearchEvidenceReadiness[]>([]);
  const [watchlistThesisStatus, setWatchlistThesisStatus] =
    useState<WatchlistThesisInitializationStatus | null>(null);
  const [daily, setDaily] = useState<InvestmentResearchDailyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [shadowStatus, setShadowStatus] = useState<PanicResearchViewState>({ kind: "loading" });
  const [shadowRunning, setShadowRunning] = useState(false);
  const [dateMode, setDateMode] = useState<PanicShadowDateMode>("auto");
  const [selectedDate, setSelectedDate] = useState(shanghaiDate());
  const [historicalReport, setHistoricalReport] = useState<HistoricalEvaluationReport | null>(null);
  const [historicalRunning, setHistoricalRunning] = useState(false);
  const [historicalError, setHistoricalError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [nextStatus, nextTheses, nextEvidence, nextAcceptedEvidence, nextReadiness, nextWatchlistThesisStatus] = await Promise.all([
        api.getInvestmentResearchStatus(),
        api.listInvestmentResearchTheses(),
        api.listInvestmentResearchEvidenceInbox("pending", 20),
        api.listInvestmentResearchEvidenceInbox("accepted", 20),
        api.listInvestmentResearchEvidenceReadiness(),
        api.getWatchlistThesisInitialization(),
      ]);
      const validCollections = Array.isArray(nextTheses)
        && Array.isArray(nextEvidence)
        && Array.isArray(nextAcceptedEvidence)
        && Array.isArray(nextReadiness);
      if (!validCollections) {
        setStatus({
          enabled: false, shadow_mode: false, schema_version: 0,
          schema_components: { research_core: 0, evidence_inbox: 0, evidence_association: 0, evidence_set_review: 0 },
          thesis_count: 0, evidence_inbox: { pending: 0, accepted: 0, rejected: 0 },
          positioning: "", output_contract: "",
        });
        setTheses([]);
        setPendingEvidence([]);
        setAcceptedEvidence([]);
        setReadiness([]);
        setWatchlistThesisStatus(null);
        setDaily(null);
      } else {
        setStatus(nextStatus);
        setTheses(nextTheses);
        setPendingEvidence(nextEvidence);
        setAcceptedEvidence(nextAcceptedEvidence);
        setReadiness(nextReadiness);
        setWatchlistThesisStatus(nextWatchlistThesisStatus);
        try { setDaily(await api.getInvestmentResearchDaily(shanghaiDate())); } catch { setDaily(null); }
      }
    } catch (reason) {
      if (isDisabledFeatureError(reason)) {
        setStatus({
          enabled: false, shadow_mode: false, schema_version: 0,
          schema_components: { research_core: 0, evidence_inbox: 0, evidence_association: 0, evidence_set_review: 0 },
          thesis_count: 0, evidence_inbox: { pending: 0, accepted: 0, rejected: 0 },
          positioning: "", output_contract: "",
        });
      } else {
        setError(reason instanceof Error ? reason.message : "读取投资研究数据失败");
      }
    }
    try {
      const shadowRaw = await api.getPanicShadowStatus();
      if (shadowRaw.date_context?.effective_trade_date) {
        setSelectedDate(shadowRaw.date_context.effective_trade_date);
      }
      if (!shadowRaw.enabled) {
        setShadowStatus(panicResearchDisabled("后端影子报告未启用"));
      } else {
        try {
          setShadowStatus(panicResearchReady(await api.getLatestPanicShadowReport()));
        } catch (reason) {
          setShadowStatus(panicResearchError(reason));
        }
      }
    } catch (reason) {
      if (isDisabledFeatureError(reason)) {
        setShadowStatus(panicResearchDisabled("影子报告后端功能未启用，需要设置 INVESTMENT_RESEARCH_ROUTES_ENABLED 和 PANIC_SHADOW_REPORT_API_ENABLED"));
      } else {
        setShadowStatus(panicResearchError(reason));
      }
    }
    setLoading(false);
  }, []);

  const runCurrentShadow = useCallback(async () => {
    setShadowRunning(true);
    try {
      setShadowStatus(panicResearchReady(await api.runCurrentPanicShadowReport({
        date_mode: dateMode,
        requested_date: dateMode === "selected" ? selectedDate : null,
      })));
    } catch (reason) {
      setShadowStatus(panicResearchError(reason));
    } finally {
      setShadowRunning(false);
    }
  }, [dateMode, selectedDate]);

  const importManualShadow = useCallback(async (file: File) => {
    setShadowRunning(true);
    try {
      if (file.size > 5 * 1024 * 1024) {
        throw new Error("manual import file exceeds 5 MiB");
      }
      const manifest = JSON.parse(await file.text()) as unknown;
      setShadowStatus(panicResearchReady(await api.runManualPanicShadowReport(
        manifest,
        {
          date_mode: dateMode,
          requested_date: dateMode === "selected" ? selectedDate : null,
        },
      )));
    } catch (reason) {
      if (reason instanceof SyntaxError || (reason instanceof Error && reason.message.includes("5 MiB"))) {
        setShadowStatus({
          kind: "error",
          errorKind: "invalid_contract",
          message: "Manual import is not valid JSON.",
          reasons: [],
        });
      } else {
        setShadowStatus(panicResearchError(reason));
      }
    } finally {
      setShadowRunning(false);
    }
  }, [dateMode, selectedDate]);

  const evaluateAutomaticHistoricalPrices = useCallback(async (
    stockCode: string,
    evaluationDate: string,
  ) => {
    setHistoricalRunning(true);
    setHistoricalError("");
    try {
      setHistoricalReport(await api.evaluateAutomaticHistoricalPrices({
        stock_code: stockCode,
        evaluation_date: evaluationDate,
        horizon: 20,
      }));
    } catch (reason) {
      setHistoricalReport(null);
      if (reason instanceof ApiError) {
        const details = reason.reasons.length > 0
          ? `\n${reason.reasons.map((item) => `• ${item}`).join("\n")}`
          : "";
        setHistoricalError(`${reason.message}${details}\n此时可展开高级选项导入 JSON。`);
      } else {
        setHistoricalError(
          reason instanceof Error ? reason.message : "自动历史行情获取失败。",
        );
      }
    } finally {
      setHistoricalRunning(false);
    }
  }, []);

  const importHistoricalPrices = useCallback(async (file: File) => {
    setHistoricalRunning(true);
    setHistoricalError("");
    try {
      if (file.size > 5 * 1024 * 1024) {
        throw new Error("历史价格文件超过 5 MiB。");
      }
      const manifest = JSON.parse(await file.text()) as unknown;
      setHistoricalReport(await api.evaluateManualHistoricalPrices(manifest));
    } catch (reason) {
      setHistoricalReport(null);
      setHistoricalError(
        reason instanceof Error ? reason.message : "历史价格导入或计算失败。",
      );
    } finally {
      setHistoricalRunning(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const versionedCount = useMemo(() => theses.filter((item) => item.research_state === "versioned").length, [theses]);
  const readinessByThesis = useMemo(
    () => new Map(readiness.map((item) => [item.thesis_id, item])),
    [readiness],
  );

  if (loading) return <div className="p-8 text-muted-foreground">正在读取研究状态…</div>;
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 lg:p-8">
      <header>
        <div className="flex items-center gap-2"><BookOpenCheck className="h-6 w-6 text-primary" /><h1 className="text-2xl font-bold">AI Investment Researcher</h1></div>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">把有限研究时间集中到少数可能被错误定价的机会；输出研究候选与否定问题，不输出交易指令。</p>
      </header>
      {error && <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
      <DailyOpportunitySection />
      <details className="rounded-xl border bg-card">
        <summary className="cursor-pointer p-4 text-sm font-semibold">
          高级工具：历史T+20评测与旧版市场回放
        </summary>
        <div className="space-y-5 border-t p-4">
          <HistoricalOutcomeSection
            report={historicalReport}
            running={historicalRunning}
            error={historicalError}
            onAutomatic={(stockCode, evaluationDate) => {
              void evaluateAutomaticHistoricalPrices(stockCode, evaluationDate);
            }}
            onImport={(file) => { void importHistoricalPrices(file); }}
          />
          <PanicShadowSection
            status={shadowStatus}
            running={shadowRunning}
            dateMode={dateMode}
            selectedDate={selectedDate}
            onDateModeChange={setDateMode}
            onSelectedDateChange={setSelectedDate}
            onRun={() => { void runCurrentShadow(); }}
            onManualImport={(file) => { void importManualShadow(file); }}
          />
        </div>
      </details>
      <section className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl border bg-card p-4"><p className="flex items-center gap-1 text-xs text-muted-foreground"><FlaskConical className="h-3.5 w-3.5" />运行模式</p><p className="mt-2 font-semibold">{status?.shadow_mode ? "Shadow Research" : "Research"}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">Thesis 覆盖</p><p className="mt-2 font-semibold">{versionedCount} / {theses.length} 已建立证据版本</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">待审证据</p><p className="mt-2 font-semibold">{status?.evidence_inbox.pending ?? pendingEvidence.length} 条</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="flex items-center gap-1 text-xs text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5" />输出边界</p><p className="mt-2 font-semibold">Research Candidate，不是交易指令</p></div>
      </section>
      {!status?.enabled && <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-700">V2 自动研究当前关闭；页面仅展示已持久化的只读研究状态。</div>}
      <ThesisInitializationPanel
        status={watchlistThesisStatus}
        onCompleted={load}
      />
      <DailyPanel report={daily} />
      <EvidenceInbox items={pendingEvidence} />
      <AcceptedEvidence items={acceptedEvidence} />
      <section>
        <div className="mb-3"><h2 className="text-xl font-semibold">AI 基础设施 Thesis Tree</h2><p className="text-sm text-muted-foreground">未初始化节点不显示 Confidence，避免把研究假设伪装成结论。</p></div>
        <div className="grid gap-4 lg:grid-cols-2">{theses.map((thesis) => (
          <ThesisCard
            key={thesis.thesis_id}
            thesis={thesis}
            readiness={readinessByThesis.get(thesis.thesis_id)}
          />
        ))}</div>
      </section>
      <footer className="rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">每项研究结论必须有证据、反方证据、失效条件和复核时间。Research output, not a trade instruction.</footer>
    </div>
  );
}
