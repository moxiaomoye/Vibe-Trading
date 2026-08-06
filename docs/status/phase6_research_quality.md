# Phase 6 — Research Quality Evaluation（历史复盘 Case Review）

Date: 2026-08-06
Status: DONE（事后复盘契约；不接入 PIT 研究流水线）

## 目的

对历史研究案例做**复盘 Case Review**（非预测胜率）：判断当时判断是否合理、
是否遗漏了事后实现的风险、案发时数据是否充分。显式边界：单次结果不能证明
研究能力。

## 契约

- `agent/src/investment_research/models/research_quality.py`（新）：
  - `QualityDimension` 三维：reasoning（判断合理性）/ risk_coverage（风险
    遗漏）/ data_sufficiency（数据充分性）。
  - `ReviewVerdict`：SOUND / ADEQUATE / PARTIAL / INSUFFICIENT /
    REVIEW_NEEDED（各维度"良好"标签不同：覆盖度用 ADEQUATE）。
  - `CaseReviewInputs`（post-hoc 输入）：data_gaps / estimated_field_count /
    materialized_unflagged_risks / reasoning_issues。
  - `evaluate_research_quality`：纯函数、确定性、冻结基准
    （gap 2/4 分档、漏标风险 1/2 分档、理由问题 1/2 分档）。
  - 总评 = 最差维度；summary 强制声明"非预测胜率"边界。

## 为何不接入冻结 report

复盘输入（已实现风险、理由问题）是**事后**信息，而冻结链路的研究报告是
**PIT 纯**契约 —— 接入会污染 point-in-time 语义。本模块作为独立复盘工具
单独使用，契约冻结文档无需变更。

## 测试

- `agent/tests/test_research_quality.py`（新，10 项）：三维分档、总评=最差
  维度、估计输入可见性、非预测胜率声明、无交易指令/无 win_rate、确定性、
  冻结基准。
- 相关套件全量回归：167 passed。
