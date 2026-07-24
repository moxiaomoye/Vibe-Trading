import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpenCheck, CircleDashed, FileCheck2, FlaskConical, Search, ShieldCheck } from "lucide-react";

import {
  api,
  isDisabledFeatureError,
  type InvestmentResearchDailyReport,
  type InvestmentResearchEvidenceInboxItem,
  type InvestmentResearchEvidenceReadiness,
  type InvestmentResearchStatus,
  type InvestmentResearchThesis,
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

function PanicShadowSection({ status, running, onRun, onManualImport }: {
  status: PanicResearchViewState;
  running: boolean;
  onRun: () => void;
  onManualImport: (file: File) => void;
}) {
  const runButton = (
    <button
      type="button"
      onClick={onRun}
      disabled={running}
      className="rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
    >
      {running ? "正在生成…" : "生成今日盘后报告"}
    </button>
  );
  const actions = (
    <div className="flex flex-wrap gap-2">
      {runButton}
      <label className={`rounded-md border px-3 py-2 text-xs font-medium ${running ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}>
        导入当日 JSON
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
    const label = status.errorKind === "authentication" ? "认证失败" :
      status.errorKind === "not_found" ? "尚无盘后报告" :
      status.errorKind === "invalid_contract" ? "响应异常" : "服务不可用";
    const description = status.errorKind === "not_found"
      ? "当前还没有已保存的可信报告，可以在收盘后手动生成。"
      : status.errorKind === "authentication"
        ? "请先在设置中填写正确的 Server API key。"
        : status.errorKind === "invalid_contract"
          ? "导入文件或后端报告不符合当前数据契约。"
          : "盘后报告服务暂时没有返回可用结果。";
    return (
      <section className="rounded-xl border border-destructive/40 bg-destructive/5 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">A股盘后恐慌初筛</h2>
            <p className="mt-2 text-sm text-destructive">{label}：{description}</p>
          </div>
          {status.errorKind !== "authentication" && actions}
        </div>
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-amber-500/30 bg-card p-5">
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
    </section>
  );
}

export function InvestmentResearch() {
  const [status, setStatus] = useState<InvestmentResearchStatus | null>(null);
  const [theses, setTheses] = useState<InvestmentResearchThesis[]>([]);
  const [pendingEvidence, setPendingEvidence] = useState<InvestmentResearchEvidenceInboxItem[]>([]);
  const [acceptedEvidence, setAcceptedEvidence] = useState<InvestmentResearchEvidenceInboxItem[]>([]);
  const [readiness, setReadiness] = useState<InvestmentResearchEvidenceReadiness[]>([]);
  const [daily, setDaily] = useState<InvestmentResearchDailyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [shadowStatus, setShadowStatus] = useState<PanicResearchViewState>({ kind: "loading" });
  const [shadowRunning, setShadowRunning] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [nextStatus, nextTheses, nextEvidence, nextAcceptedEvidence, nextReadiness] = await Promise.all([
        api.getInvestmentResearchStatus(),
        api.listInvestmentResearchTheses(),
        api.listInvestmentResearchEvidenceInbox("pending", 20),
        api.listInvestmentResearchEvidenceInbox("accepted", 20),
        api.listInvestmentResearchEvidenceReadiness(),
      ]);
      setStatus(nextStatus);
      setTheses(nextTheses);
      setPendingEvidence(nextEvidence);
      setAcceptedEvidence(nextAcceptedEvidence);
      setReadiness(nextReadiness);
      try { setDaily(await api.getInvestmentResearchDaily(shanghaiDate())); } catch { setDaily(null); }
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
      setShadowStatus(panicResearchReady(await api.runCurrentPanicShadowReport()));
    } catch (reason) {
      setShadowStatus(panicResearchError(reason));
    } finally {
      setShadowRunning(false);
    }
  }, []);

  const importManualShadow = useCallback(async (file: File) => {
    setShadowRunning(true);
    try {
      if (file.size > 5 * 1024 * 1024) {
        throw new Error("manual import file exceeds 5 MiB");
      }
      const manifest = JSON.parse(await file.text()) as unknown;
      setShadowStatus(panicResearchReady(await api.runManualPanicShadowReport(manifest)));
    } catch (reason) {
      if (reason instanceof SyntaxError || (reason instanceof Error && reason.message.includes("5 MiB"))) {
        setShadowStatus({
          kind: "error",
          errorKind: "invalid_contract",
          message: "Manual import is not valid JSON.",
        });
      } else {
        setShadowStatus(panicResearchError(reason));
      }
    } finally {
      setShadowRunning(false);
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
      <PanicShadowSection
        status={shadowStatus}
        running={shadowRunning}
        onRun={() => { void runCurrentShadow(); }}
        onManualImport={(file) => { void importManualShadow(file); }}
      />
      <section className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl border bg-card p-4"><p className="flex items-center gap-1 text-xs text-muted-foreground"><FlaskConical className="h-3.5 w-3.5" />运行模式</p><p className="mt-2 font-semibold">{status?.shadow_mode ? "Shadow Research" : "Research"}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">Thesis 覆盖</p><p className="mt-2 font-semibold">{versionedCount} / {theses.length} 已建立证据版本</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">待审证据</p><p className="mt-2 font-semibold">{status?.evidence_inbox.pending ?? pendingEvidence.length} 条</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="flex items-center gap-1 text-xs text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5" />输出边界</p><p className="mt-2 font-semibold">Research Candidate，不是交易指令</p></div>
      </section>
      {!status?.enabled && <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-700">V2 自动研究当前关闭；页面仅展示已持久化的只读研究状态。</div>}
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
