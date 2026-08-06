# CURRENT STATE — Vibe-Trading 长期维护 Handoff

更新：2026-08-06（Phase 1 完成；Phase 1.5 完成；Phase 2 进行中）
模式：LOCAL DEVELOPMENT MODE（禁止 push/PR/merge/remote 同步；本地 commit 仅
为 checkpoint，`--no-gpg-sign`）

---

## 当前阶段

- **Phase 2（Regime Detection）进行中**：Macro State 基础契约（contract-first）。
- Phase 1（Market Intelligence）与 Phase 1.5（Historical Data Quality）已完成。
- Phase 0–0.8（架构审计 / Contract / Context 迁移 / 契约冻结）全部完成。

## 已完成

- **Phase 0–0.8**：ResearchContract、ResearchContext 接管数据流、Artifact
  可复现（data_snapshot_id + research_run_id）、Contract Enforcement 测试。
- **Phase 1**：`market_intelligence` 引擎（NORMAL/STRESS/PANIC/EXTREME_PANIC/
  UNKNOWN），六维（指数/宽度/涨跌停/成交/波动率/ERP），维度感知可用性，无交易
  指令，PIT 安全，确定性可复现；已接入 ResearchContext + report + 存储往返。
- **Phase 1.5（commit e1b13c1）**：历史回溯真实化 —— 跌停/涨停数量基于研究标的池
  估计（±9.8% 近似，与 live 路径同口径），仅用目标日已发布 bar（PIT 安全），显式
  标注 ESTIMATED：
  - `MarketObservation.estimated_fields` → `MarketSnapshotModel.estimated_fields`
    → DataQuality `ESTIMATED`（原因注明"基于研究标的池"）。
  - 引擎：LIMIT 维度判定 ESTIMATED（note 显式标注）；ESTIMATED 证据**不计入**
    可用权重（仅 AVAILABLE 归一化）；coverage 增加 `estimated` 计数。
  - 警告拆分：宽度=标的池标注、跌停/涨停=估计标注、成交额分位=仍为 Data Gap。
  - 缓存校验按 required_summary 键，新字段向后兼容（旧缓存缺省空列表）。
- 测试：97 passed（相关套件全量，含新增 3 引擎 + 1 契约传导）。

## 未完成 / 下一步

1. **Phase 2**：Regime Detection（Macro State 基础契约）：MacroDimension 五维
   （利率/流动性/ERP/盈利/信贷）；Regime 枚举 LIQUIDITY_PANIC/
   EARNINGS_DOWNGRADE/STRUCTURAL_REPRICING/STABLE/UNKNOWN；contract-first 纯
   函数；数据源未接入时输出 UNKNOWN + 显式缺口；无交易指令、确定性、PIT 安全。
2. **Phase 3**：ETF/指数研究层（指数代理优先，禁止复杂复制计算）。
3. 长期维护项：Provider 健康 / 依赖变化 / 数据源变化 / 架构违规周检。

## 风险

- 阈值（-2.0% / -20% / 0.30 / 50 / 1.5σ）为经验值：变更必须走
  MarketIntelligenceConfig 版本化，不得裸改常量。
- 历史估计（标的池 ±9.8%）是显式标签的估计，**永远不得**冒充全市场统计；
  成交额分位仍未接入（Data Gap），禁止静默填充。
- 本地 commit 为 checkpoint，格式 feat:/fix:/refactor:/docs:，无 DCO。

## 关键文件

- `agent/src/value_hunter/providers.py`（历史路径估计 + estimated_fields 标注）
- `agent/src/value_hunter/models.py`（MarketObservation.estimated_fields）
- `agent/src/investment_research/models/market_intelligence.py`（Phase 1 引擎）
- `agent/src/investment_research/models/research_context.py`（attach/context/
  ESTIMATED DataQuality 传导）
- `agent/tests/test_market_intelligence.py`、`test_research_contract_models.py`
- `automation/long_runner.py` + `tasks/roadmap.yaml`（任务队列，P2 in_progress）
- `docs/status/phase0_8_contract_freeze.md`、`docs/status/phase1_market_intelligence.md`
