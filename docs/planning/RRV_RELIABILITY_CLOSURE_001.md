# RRV-RELIABILITY-CLOSURE-001 — 真实研究可靠性收口规格

日期：2026-08-07
状态：规格已冻结，进入实现

## 本轮范围
修复 RRV 首轮暴露的核心缺陷，使历史研究报告具备：完整候选研究合同、有限重试/节流/熔断/可审计退化、严格历史资格判断、可解释多信号触发证据、版本化市场状态协调、真实数据重跑验证。不新增交易功能。

## 输入输出合同

### P0-1 候选合同（共享 Contract Builder，三路径统一）
```
{name, code, security_type, eligibility_as_of, research_status, score,
 score_components{mispricing,quality,valuation,relative_strength,catalyst,total},
 selection_reasons[], first_rejection, missing_fields[], data_gaps[],
 source_fields[], provider_warnings[], supporting_evidence[], counter_evidence[],
 risk_review{}, forward_validation{t5,t20,t60}}
```
- 路径：实时 / 已存快照回放 / HistoricalAkshareProvider 重建 / RRV 全部走同一 builder；
- C 状态候选也必须输出确定性 score 与 score_components（源自 ScoreBreakdown，确定性）；
- ETF 不适用的公司财务字段显式 `NOT_APPLICABLE`；股票缺失为 `MISSING`（None + 进入 missing_fields）；
- 现有 API 字段（current_price、entry_reasons、research_plan 等）保持向后兼容（保留输出）。

### P0-2 公共端点调用策略（PublicEndpointPolicy）
- 覆盖：stock_value_em、stock_financial_analysis_indicator、未来同类逐标的公共端点；
- 参数：endpoint_name / timeout_seconds / max_attempts(默认3) / initial_backoff / max_backoff / endpoint_min_interval / retryable 分类 / run 级熔断 / 统计 / 可注入 sleep+clock；
- 重试白名单：RemoteDisconnected、ConnectionError、TimeoutError、TLS reset、HTTP 429、HTTP 5xx；
- 不重试：字段缺失、Schema 变化、KeyError、非法数据日期、解析错误、明确 4xx 业务拒绝；
- 熔断：同一 run 连续失败 >= 3 次 → 该端点 DEGRADED，剩余标的跳过（记录 provider_health + gap），下一次独立 run 重新尝试；
- 并发：同一端点最大并发 1（串行）；不同端点可有限并行；
- 失败耗尽：保留原异常类别、写 provider health、字段标 UNAVAILABLE、不阻塞市场层报告、不伪造成功。

### P0-3 Provider Health
每份 Research Artifact 增加 `provider_health`：
```
{providers: [{endpoint, provider, attempts, successes, failures,
  state: HEALTHY|DEGRADED|UNAVAILABLE|NOT_USED,
  last_error_type, last_error_summary, cooldown_triggered}]}
```
- 不记录 Token/密码/Cookie/完整请求头；错误摘要限长 200 字符；
- content_hash 覆盖 report 全内容 → provider_health 自动进入 Artifact Hash；
- 缓存复用记录 cache_hit + 原始 as_of（数据发布截至日）。

### P0-4 PIT 安全运行缓存
- key：provider + endpoint + symbol + requested_as_of + provider_version + schema_version；
- 只缓存成功结果；raw 抓取时间戳与 normalized（PIT 过滤后）分字段保存；
- 缓存损坏 → 显式失效并重新抓取；不缓存失败；缓存文件不入 Git（放 runtime cache 目录）。

### P1 资格合同（历史可投资标的）
- 状态：`ELIGIBLE` / `CONFIRMED_NOT_LISTED` / `UNKNOWN`；
- 字段：eligibility_status / listing_date / eligibility_evidence_source / eligibility_reason / eligibility_as_of；
- 判断优先级：① watchlist/资产元数据 listing_date → ② Loader Registry 上市信息（未接入则跳过）→ ③ as_of 前存在可验证交易记录 → ④ 无法确认 UNKNOWN；
- listing_date > as_of → CONFIRMED_NOT_LISTED：排除出候选评分与 Top5，保留在 universe_audit；
- as_of 前存在交易记录 → ELIGIBLE；Provider 失败且无交易数据 → UNKNOWN（禁止把 Provider 故障冒充上市日判断）；
- 允许 watchlist.yaml 增加可选 listing_date（仅补充 588060/159941 两个已确认上市日的 ETF，其余不强制补齐）；
- 禁止 `if code == "588060"` 式硬编码。

### P1 Universe Audit
历史报告增加 `universe_audit`：每个标的输出 symbol/name/security_type/eligibility_status/listing_date/selected/exclusion_reason/data_status/data_as_of/data_source/data_gaps；被排除标的仍可审计，但不进入正式 Research Candidate 列表。

### P2 Market Intelligence 触发证据
- 新增 `MarketSignalVerdict{signal,status,observed,threshold,comparator,triggered,note}`；
- MarketDimensionVerdict 增加 `signals[]`；observed/threshold/triggered 保留为摘要字段，triggered = 任一有效子信号触发；
- index：median_daily_return / median_drawdown / all_indices_below_ma250 / all_indices_below_120d_low；
- breadth：advancer_ratio / above_ma60_ratio；limit、turnover 同构；
- summary 只描述真实触发的信号；ESTIMATED 不单独计入 available weight（现状保持）。

### P3 版本化市场状态协调（预注册规则，禁止反向调参）
- 新增 `MarketStateReconciliation`：
```
{policy_version: "market-state-reconcile-v1", legacy_state, intelligence_state,
 effective_state, conflict, coverage_gate_passed, reasons[], data_limitations[]}
```
- 严重度顺序：NORMAL < CAUTION/STRESS < PANIC < EXTREME_PANIC（UNKNOWN 不参与比较）；
- **规则（冻结）**：
  1. coverage_gate_passed = (intel.state != UNKNOWN) AND (AVAILABLE 维度数 >= 2) AND (INDEX 或 BREADTH 属于 AVAILABLE) AND (至少一个 AVAILABLE 维度触发 —— 不依赖仅 ESTIMATED 触发)；
  2. gate 通过 → effective = legacy 与 intel 中更严重者；gate 不通过 → effective = legacy；
  3. ESTIMATED 维度可展示，不单独推动升级；
  4. 新状态不得因缺数据把旧严重状态降级（effective >= legacy 恒成立）；
  5. conflict = legacy 与 intel 严重度不一致（intel UNKNOWN 不构成 conflict，记 data_limitations）；
  6. 所有冲突显式输出，不静默覆盖。
- API：保留 market_state（=legacy 兼容字段）；新增 legacy_market_state / effective_market_state / market_state_reconciliation；不删除旧字段；
- 通知发送条件不改（通知默认关闭、需人工确认）。

### P4 验证 Runner v2
- `automation/research_validation_v2.py` → `docs/research_validation_v2/`：manifest.json / provider_health.json / 5 事件报告 / validation_summary.json / reproducibility_report.json / RRV_V2_REVIEW.md / failures.jsonl；
- 逐事件、事件间 cooldown、每事件独立 raw provider 诊断、单事件失败不覆盖其他事件；
- 独立 run namespace：独立 SQLite（data/rrv2/）+ 独立缓存，不复用首轮错误快照；
- 不发送飞书/邮件、不产生交易通知、不读未来数据；forward return 仅用于事后复盘。

## 兼容策略
- market_state 保留；新字段全部为增量添加；候选旧字段保留；
- 老快照回放：snapshot 缺新字段时按缺失/UNKNOWN 处理，不报错；
- 前端 TS 类型同步扩展，旧字段类型不变。

## 失败状态
- 真实端点仍不可用 → 报告标 `DATA_SOURCE_BLOCKED`（报告级原因），候选字段 UNAVAILABLE，不得伪造修复成功；
- 2015 估值结构性缺口（RF-006）、Macro 未接入（RF-007）维持 ACCEPTED_* 状态，不伪装。

## 验收标准
1. 5 事件全部生成报告或明确 DATA_SOURCE_BLOCKED；
2. 所有候选均有 score/score_components/first_rejection/missing_fields/data_gaps/risk_review；
3. Stored 与 Rebuilt 候选 Schema 一致；
4. 模拟 RemoteDisconnected 有限重试后恢复；连续失败 → DEGRADED 不轰炸；端点失败不使市场报告消失；
5. 缓存 PIT 安全（无未来泄漏）、损坏显式失效、二次运行复用；
6. 2015 报告 588060 非 Research Candidate，universe_audit 显示排除原因；UNKNOWN 与 CONFIRMED_NOT_LISTED 严格区分；
7. 5 事件保留 legacy/intelligence/effective 三状态；2024 冲突可解释（宽度/回撤/趋势证据，非伪造指数暴跌）；
8. RF-004 触发信号清晰展示；前端显示状态冲突与子信号；Data Gap 显式存在；
9. 不强行制造 A/B 候选；C 候选也完整。
10. 全量 pytest 不降级（基线 1038 passed / 5 skipped，新增测试只增不减）；frontend typecheck+build 通过。

## 不做事项
- 新 Macro 数据源；修复 RF-006 上游 2015 估值历史；RF-007 伪装有数据；自动交易/券商接入/价格预测/仓位建议；
- 修改历史 forward return 定义；用事后收益调整当时评分；自动推送飞书；多 Agent/Swarm 重构；重设计 IR V2；
- hkuds 同步/合并/push；强制推送；清理历史提交；无关重构。
