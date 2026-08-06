# Phase 2 — Regime Detection（Macro State 基础契约）

Date: 2026-08-06
Status: DONE（contract-first；宏观数据源未接入，缺口显式保留）

## 目的

在 Phase 1（市场状态）之上增加宏观层面（Macro State）的判定契约。本阶段只
冻结契约与引擎（纯函数、确定性、PIT 安全），**不接入任何宏观数据源**：
数据源未接入时输出 UNKNOWN + 显式缺口，绝不静默猜测。

## 契约

- `agent/src/investment_research/models/market_regime.py`（新）：
  - `Regime`：LIQUIDITY_PANIC / EARNINGS_DOWNGRADE / STRUCTURAL_REPRICING /
    STABLE / UNKNOWN。
  - `MacroDimension` 五维：rate（利率）/ liquidity（流动性）/ erp / earnings
    （盈利）/ credit（信贷）。
  - `MacroSnapshotModel`：PIT 宏观输入（as_of/source/coverage/warnings/
    estimated_fields + 五维可空观测值）。缺失输入 = 显式 Data Gap，绝不静默为零。
  - `MarketRegimeConfig`（冻结阈值，版本化 market-regime-v1）：
    利率上行 50bp / 融资利差 100bp / ERP 5.0% / EPS 修正 ≤-3.0% / 信用利差 200bp；
    权重 30/25/20/15/10 = 100。
  - `evaluate_market_regime`：纯函数，无 I/O、无未来数据。
- Regime 是**分类判定**而非压力连续分：三种危机情景性质不同，采用文档化优先级
  判定：**流动性冲击 > 盈利下调潮 > 结构重定价**，冲突在 summary 中显式说明。

## 可用性与估计

- 维度输入缺失 → `UNAVAILABLE` + 显式缺口 note；无可用证据 → UNKNOWN。
- `estimated_fields` 输入 → `ESTIMATED` + 标注，**不计入**可用证据权重
  （与 Phase 1/1.5 口径一致）。
- coverage：`{"available", "estimated", "total": 5}`。

## 接线（冻结链路）

- `ResearchContext.macro_snapshot` / `market_regime`（均可选字段）；
  `from_scan_payload` 从 `payload["macro"]["observation"]` 构建并评估。
- `attach_contract_metadata` 写入报告顶层键 `market_regime`
  （`_market_regime_block`：无 macro 快照时输出确定性 UNKNOWN 兜底块）。
- 契约冻结变更记录：phase0_8_contract_freeze.md（键集 + market_regime）。

## 测试

- `agent/tests/test_market_regime.py`（新，16 项）：分类优先级/可用性与缺口/
  估计排除/契约形状（确定性、版本、阈值冻结、无交易指令）。
- `test_research_contract_models.py`：macro 接线、roundtrip 确定性、UNKNOWN
  兜底；`test_research_mvp_routes.py`：顶层键集更新。
- 相关套件回归：117 passed。

## 未接入（显式缺口，禁止假装）

- 利率 / 资金面 / ERP / EPS 修正 / 信用利差：均无数据源接入；scan payload 带
  `macro.observation` 时才评估，否则 UNKNOWN。
