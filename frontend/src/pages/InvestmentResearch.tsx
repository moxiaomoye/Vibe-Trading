import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpenCheck, CircleDashed, FileCheck2, FlaskConical, Search, ShieldCheck } from "lucide-react";

import {
  api,
  type InvestmentResearchDailyReport,
  type InvestmentResearchEvidenceInboxItem,
  type InvestmentResearchEvidenceReadiness,
  type InvestmentResearchStatus,
  type InvestmentResearchThesis,
} from "@/lib/api";


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

export function InvestmentResearch() {
  const [status, setStatus] = useState<InvestmentResearchStatus | null>(null);
  const [theses, setTheses] = useState<InvestmentResearchThesis[]>([]);
  const [pendingEvidence, setPendingEvidence] = useState<InvestmentResearchEvidenceInboxItem[]>([]);
  const [acceptedEvidence, setAcceptedEvidence] = useState<InvestmentResearchEvidenceInboxItem[]>([]);
  const [readiness, setReadiness] = useState<InvestmentResearchEvidenceReadiness[]>([]);
  const [daily, setDaily] = useState<InvestmentResearchDailyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
      setError(reason instanceof Error ? reason.message : "读取投资研究数据失败");
    } finally {
      setLoading(false);
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
