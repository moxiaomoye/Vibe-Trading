import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, RefreshCw, ShieldAlert } from "lucide-react";
import { api, isDisabledFeatureError, type ValueHunterCandidate, type ValueHunterScan, type ValueHunterStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

function scoreTone(score: number) {
  if (score >= 85) return "text-red-500";
  if (score >= 70) return "text-orange-500";
  if (score >= 50) return "text-amber-500";
  return "text-emerald-500";
}

function CandidateCard({ candidate }: { candidate: ValueHunterCandidate }) {
  const obs = candidate.observation;
  return (
    <article className="rounded-xl border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-lg">{obs.name}</h3>
            <span className="font-mono text-xs text-muted-foreground">{obs.symbol}</span>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{candidate.bucket}</span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{obs.sector} · {obs.theme}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold">{candidate.score.total.toFixed(1)}</p>
          <p className="text-xs text-muted-foreground">{candidate.status}</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
        {[
          ["质量", candidate.score.quality], ["估值", candidate.score.valuation],
          ["基本面", candidate.score.fundamentals], ["错杀", candidate.score.dislocation],
          ["风险洁净", candidate.score.risk_cleanliness],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-md bg-muted/60 p-2">
            <p className="text-muted-foreground">{label}</p><p className="font-semibold">{Number(value).toFixed(1)}</p>
          </div>
        ))}
      </div>
      <ul className="mt-4 space-y-1 text-sm">
        {candidate.reasons.map((reason) => <li key={reason}>· {reason}</li>)}
      </ul>
      <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
        <span className="font-medium">首要否决项：</span>{candidate.first_rejection}
      </div>
      {candidate.missing_fields.length > 0 && (
        <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
          <Database className="h-3.5 w-3.5" />缺失字段：{candidate.missing_fields.join(", ")}
        </p>
      )}
    </article>
  );
}

export function ValueHunter() {
  const [status, setStatus] = useState<ValueHunterStatus | null>(null);
  const [scan, setScan] = useState<ValueHunterScan | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const value = await api.getValueHunterStatus();
      setStatus(value);
      setScan(value.latest);
    } catch (err) {
      if (isDisabledFeatureError(err)) {
        setStatus({
          enabled: false, provider: "", schedule: "", timezone: "",
          notification_channels: [], notification_ready: true,
          missing_notification_settings: [], latest: null,
        });
      } else {
        setError(err instanceof Error ? err.message : "读取失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const run = async () => {
    setRunning(true); setError("");
    try {
      const result = await api.runValueHunter(false);
      setScan(result);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "扫描失败");
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <div className="p-8 text-muted-foreground">正在读取 Value Hunter…</div>;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 lg:p-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2"><ShieldAlert className="h-6 w-6 text-primary" /><h1 className="text-2xl font-bold">Value Hunter</h1></div>
          <p className="mt-1 text-sm text-muted-foreground">A股科技恐慌监控与研究候选筛选，不执行交易。</p>
        </div>
        <button onClick={run} disabled={running} className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
          <RefreshCw className={cn("h-4 w-4", running && "animate-spin")} />{running ? "扫描中" : "立即扫描"}
        </button>
      </header>

      {error && <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}

      <section className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">服务状态</p><p className="mt-2 flex items-center gap-2 font-semibold">{status?.enabled ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <AlertTriangle className="h-4 w-4 text-amber-500" />}{status?.enabled ? "自动运行" : "仅手动运行"}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">数据源</p><p className="mt-2 font-semibold uppercase">{status?.provider ?? "—"}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">执行时间</p><p className="mt-2 font-semibold">{status?.schedule ?? "—"} <span className="text-xs font-normal text-muted-foreground">{status?.timezone}</span></p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">通知通道</p><p className="mt-2 font-semibold">{status?.notification_channels.length ? status.notification_channels.join(" + ") : "尚未配置"}</p></div>
      </section>

      {status && !status.notification_ready && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-700">
          提醒通道尚未启用。缺少配置：{status.missing_notification_settings.join("、")}。
        </div>
      )}

      {!scan ? (
        <section className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">尚无扫描记录，点击“立即扫描”生成第一份报告。</section>
      ) : (
        <>
          <section className="rounded-xl border bg-card p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div><p className="text-sm text-muted-foreground">市场状态 · {scan.market.observation.as_of}</p><h2 className={cn("mt-1 text-3xl font-bold", scoreTone(scan.market.score))}>{scan.market.level} {scan.market.score.toFixed(1)}/100</h2></div>
              <div className="grid grid-cols-4 gap-2 text-center text-xs">
                {Object.entries(scan.market.components).map(([key, value]) => <div key={key} className="min-w-16 rounded-md bg-muted p-2"><p className="text-muted-foreground">{{ trend: "趋势", drawdown: "回撤", breadth: "宽度", panic: "恐慌" }[key] ?? key}</p><p className="font-semibold">{value.toFixed(1)}</p></div>)}
              </div>
            </div>
            <ul className="mt-4 grid gap-2 text-sm sm:grid-cols-2">{scan.market.reasons.map((reason) => <li key={reason} className="rounded-md bg-muted/50 p-2">{reason}</li>)}</ul>
            {scan.market.observation.warnings.length > 0 && <p className="mt-4 text-xs text-amber-600">数据提示：{scan.market.observation.warnings.join("；")}</p>}
          </section>

          <section>
            <div className="mb-3 flex items-end justify-between"><div><h2 className="text-xl font-semibold">研究候选</h2><p className="text-sm text-muted-foreground">只展示数据完整且达到门槛的公司。</p></div><span className="text-sm text-muted-foreground">{scan.candidates.length} 家</span></div>
            <div className="grid gap-4 lg:grid-cols-2">{scan.candidates.map((candidate) => <CandidateCard key={candidate.observation.symbol} candidate={candidate} />)}</div>
            {scan.candidates.length === 0 && <div className="rounded-xl border border-dashed p-8 text-center text-muted-foreground">本轮没有达到研究门槛且数据完整的候选。</div>}
          </section>
          <footer className="rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">结果仅用于缩小研究范围。候选仍需核对最新公告、财报发布日期、盈利持续性和估值假设。</footer>
        </>
      )}
    </div>
  );
}
