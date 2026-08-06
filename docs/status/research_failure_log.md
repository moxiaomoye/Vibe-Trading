# Research Failure Log（真实研究验证）

规则：**先记录，后修复**；只修影响报告可信度的问题；禁止修复时引入新架构。

## 2026-08-06 首轮真实验证（5 历史事件，全量真实数据）

运行：`python automation/research_validation.py`（真实网络，未改生产代码）。

### RF-001 候选层完全空转：5 事件 25 个候选全部 `C - 数据不足`，0 个可评分
- 现象：全部报告 `candidates` 无 `score`/`score_components`/`selection_reasons`；`risk_review` 缺失。
- 根因：批量连续运行时 eastmoney（估值 `stock_value_em`）与 sina（财务 `stock_financial_analysis_indicator`）端点被 `RemoteDisconnected` 断连（限流/反爬）。**单独调用均正常**（sina 98 行、eastmoney 2085 行）→ 判定为批量连续调用被断连，非端点死亡。
- 可信度影响：**高**。报告只有市场层结论，个股层研究完全缺失。
- 状态：已记录。后续修复候选：provider 层重试/退避，或分批运行（未实施）。

### RF-002 2024-02-05 顶层 `market_state=CAUTION`，与 `market_intelligence=EXTREME_PANIC` 冲突
- 现象：千股跌停微盘股踩踏日，传统恐慌方法仅判 CAUTION；intel 模型判 EXTREME_PANIC（stress 100，宽度 12%）。
- 根因：传统方法以大盘指数日跌幅（沪深300 当日 -1.4%、指数中位 -1.0% vs 阈值 -2.0%）为门槛，微盘结构性踩踏在大盘指数口径不显著；intel 因回撤 -31% 与均线/低点条件触发。
- 可信度影响：**高**。结构性恐慌（微盘、小盘）在顶层状态中失灵。
- 状态：已记录。人工审查确认 intel 判定更贴近事实；传统方法灵敏度问题留待后续设计（未实施）。

### RF-003 2015-06-26 报告候选含未上市 ETF 588060（科创50ETF，2020-11 上市）
- 现象：2015 报告候选名单含 588060.SH。
- 根因：历史快照未按上市日期过滤 ETF 池。
- 可信度影响：**中**。PIT 机制挡住了指标污染（t5/t20/t60 全 null、outcome 不确定、显式 gap `base_trade_date_price`、状态 C），但候选名单本身呈现了当时不存在的投资标的。
- 状态：已记录。后续修复候选：历史路径按上市日过滤（未实施）。

### RF-004 market_intelligence index 维度 verdict 展示误导
- 现象：2024-02-05 报告显示 observed 中位日跌幅 -1.0%（阈值 -2.0%）却 `triggered=true`；实际由回撤 -31%（阈值 -20%）触发，verdict 仅展示中位跌幅。
- 根因：verdict 单字段展示，未输出实际触发的子条件。
- 可信度影响：**中**（展示层面，逻辑正确）。
- 状态：已记录。后续可输出触发子条件明细（未实施）。

### RF-005 数据源可用性现状（2026-08-06 实测）
- tushare：无 token，恒走回退（预期内）；akshare 东财：间歇断连（见 RF-001）；腾讯：指数+个股均稳定（5183 行指数、个股 25 行/月均正常）→ 5 份报告顶部 `数据源使用腾讯备用行情` 警告。
- 可信度影响：低-中（警告已显式呈现）。
- 状态：已记录，不修（腾讯回退链路工作正常）。

### RF-006 2015 年 PIT 估值结构性缺失
- 现象：2015 事件估值维度无法重建。
- 根因：`stock_value_em` 数据仅回溯至 **2018-01-02**，早于该日的估值结构性不可得（与端点健康无关）。
- 可信度影响：中（2015 报告估值维度永久缺失，应视为已知限制）。
- 状态：已记录，不修（数据源上游限制）。

### RF-007 `market_regime` 恒 UNKNOWN（非新问题）
- 现象：5 事件 regime 全部 UNKNOWN（coverage 0/5）。
- 根因：Macro 数据源未接入，P2 已显式声明为 Data Gap。
- 可信度影响：低（显式缺口，非静默）。
- 状态：已知，未计划（用户禁止新数据源接入）。

## 2026-08-07 收口（RRV-RELIABILITY-CLOSURE-001，v2 重跑）

实现 `docs/planning/RRV_RELIABILITY_CLOSURE_001.md`（provider 弹性、PIT 资格、候选合同、
信号明细、状态协调、universe 审计、数据源健康），并用 `automation/research_validation_v2.py`
独立库（`data/rrv2/`）重跑 5 事件。逐项更新如下：

### RF-001 → RESOLVED
- 修复：`PublicEndpointPolicy`（重试/指数退避/最小间隔/熔断/超时）+ `PitEndpointCache` 落地，
  `_enrich_candidate` 与两条 PIT 路径全部接入；候选合同三路径统一（`candidate-contract-v1`）。
- 验证：v2 重跑 5 事件，`stock_value_em`/`stock_financial_analysis_indicator` 双端点全部
  HEALTHY、零失败、零熔断；全部候选带 `score`/`score_components`/`risk_review`/`selection_reasons`。

### RF-002 → RESOLVED
- 修复：`market_state_reconciliation`（冻结规则：覆盖门槛通过且更严重才升级，绝不降级）。
- 验证：2024-02-05 legacy=CAUTION → effective=EXTREME_PANIC（gate passed，intelligence
  EXTREME_PANIC），与 intel 判定一致且顶层 `market_state` 键保持既有语义。

### RF-003 → RESOLVED
- 修复：`eligibility-v1` 优先级链（元数据上市日 → 交易记录 → Provider 故障=UNKNOWN）+ watchlist
  `listing_date` 元数据 + 全池 `universe_audit`。
- 验证：2015-06-26 中 588060（2020-11-16 上市）CONFIRMED_NOT_LISTED 并排除出候选；
  159941（2015-03-24 上市）凭元数据 ELIGIBLE；无元数据且无记录者为 UNKNOWN（不冒充未上市）。

### RF-004 → RESOLVED
- 修复：`MarketSignalVerdict` 子信号明细（index 四信号、breadth 两信号），verdict 逐信号给出
  observed/threshold/triggered。
- 验证：v2 报告 index 维度可见 `index_daily_return`（-1.0% vs -2.0% 未触发）与
  `index_drawdown`（-31% vs -20% 触发）等独立记录，不再单字段误导。

### RF-005 → ACCEPTED_DATA_SOURCE_LAYER
- 保持：腾讯回退链路工作正常且警告显式呈现；v2 中双端点零失败（重试吸收间歇断连）。

### RF-006 → ACCEPTED_DATA_SOURCE_BLOCKED
- 保持：`stock_value_em` 仅回溯 2018-01-02，2015 估值维度结构性缺失为上游限制；
  v2 报告 2015 事件 data_gaps 显式列出，不伪装。

### RF-007 → ACCEPTED_PLANNED
- 保持：P2 已显式声明为 Data Gap；用户禁止新数据源接入，不计划。
