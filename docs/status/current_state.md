# CURRENT STATE — Vibe-Trading 长期维护 Handoff

更新：2026-08-06（Phase 1 完成）
模式：LOCAL DEVELOPMENT MODE（禁止 push/PR/merge/remote 同步；本地 commit 仅
为 checkpoint）

---

## 当前阶段

- Phase 1（Market Intelligence Layer）核心已完成：Market State Engine +
  Market Intelligence Contract 已接入冻结链路。
- Phase 0–0.8（架构审计 / Contract / Context 迁移 / 契约冻结）全部完成。

## 已完成

- **Phase 0–0.8**：ResearchContract、ResearchContext 接管数据流、Artifact
  可复现（data_snapshot_id + research_run_id）、Contract Enforcement 测试。
- **Phase 1**：`market_intelligence` 引擎（NORMAL/STRESS/PANIC/EXTREME_PANIC/
  UNKNOWN），维度感知可用性（指数/宽度/涨跌停/成交/波动率/ERP），无交易指令，
  PIT 安全，确定性可复现；已接入 ResearchContext + report + 存储往返。
- 测试：97 passed（引擎 11 + 契约/路由/强制/既有 86）。

## 未完成 / 下一步

1. **Phase 1 收尾可选**：历史路径仅 2/6 维度可用 —— 可考虑给
   HistoricalAkshareProvider 补充跌停数量历史接入（数据真实性优先级高，但
   需动 provider，需谨慎评估 PIT 安全）。
2. **Phase 2**：Regime Detection（Macro State：利率/流动性/ERP/盈利/信贷）。
3. **Phase 3**：ETF/指数研究层（指数代理优先，禁止复杂复制计算）。
4. 长期维护项：Provider 健康 / 依赖变化 / 数据源变化 / 架构违规周检。

## 风险

- 阈值（-2.0% / -20% / 0.30 / 50 / 1.5σ）为经验值：变更必须走
  MarketIntelligenceConfig 版本化，不得裸改常量。
- 历史数据缺口（跌停/zscore）显式保留 —— 禁止用估算掩盖。
- 本地未提交 git；提交为 checkpoint，格式 feat:/fix:/refactor:/docs:，无 DCO。

## 关键文件

- `agent/src/investment_research/models/market_intelligence.py`（Phase 1 新）
- `agent/src/investment_research/models/research_context.py`（attach/context）
- `agent/src/investment_research/application/research_mvp.py`（三路径接线）
- `agent/tests/test_market_intelligence.py`、`test_research_contract_enforcement.py`
- `docs/status/phase0_8_contract_freeze.md`、`docs/status/phase1_market_intelligence.md`
