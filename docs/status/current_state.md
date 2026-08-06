# CURRENT STATE — Vibe-Trading 长期维护 Handoff

更新：2026-08-06（Phase 1–6 全部完成；进入持续维护期）
模式：LOCAL DEVELOPMENT MODE（禁止 push/PR/merge/remote 同步；本地 commit 仅
为 checkpoint，`--no-gpg-sign`）

---

## 当前阶段

- **路线图 Phase 1–6 全部完成**（tasks/roadmap.yaml 队列清空）。
- 当前状态：**maintenance-weekly**（Provider 健康 / 测试状态 / 依赖变化 /
  数据源变化 / 架构违规周检，优先修复稳定性）。

## 已完成（本session，按提交顺序）

| Phase | 提交 | 内容 |
|---|---|---|
| 1.5 | `e1b13c1` | 历史涨跌停标的池估计 + `estimated_fields` 全链路（ESTIMATED 不占可用权重） |
| — | `f44f6a8` | 交接文档更新 |
| 2 | `f96fe9e` | Regime Detection：Macro 五维契约 + UNKNOWN 显式缺口，报告键 `market_regime` |
| 3 | `b0db04f` | ETF Research Layer：指数代理风险收益/恐慌统计（PIT 截至估值 as-of，v4） |
| 4 | `c3c88d3` | Stock Risk Analyzer：`risk_review` 契约（五维价值陷阱审查，无评级指令） |
| 5 | `cd6ed81` | Fear Memory：策展危机案例库 + PIT 查询，报告键 `fear_memory` |
| 6 | `c31302e` | Research Quality Eval：事后 Case Review 契约（非预测胜率） |
| maintenance | `0d592f8` | factors registry 测试 symlink 无权限时干净跳过（WinError 1314） |

## 测试状态

- 全量套件：**1038 passed, 5 skipped**（修复后 factors registry 的 9 项
  环境依赖测试干净跳过；其余全绿）。
- 研究/价值猎人相关套件：167 passed。

## 未完成 / 下一步（维护期）

1. **maintenance-weekly**：跑全量测试、检查 provider 端点健康（AKShare 依赖
   外部接口，可能漂移）、依赖版本变化、新警告（如 pct_change fill_method
   FutureWarning 已在全量输出中出现，可评估是否收敛）。
2. 可选增强（均需先设计再动契约）：
   - 历史路径补 ETF 底层指数估值（当前历史回溯为 Data Gap，见 providers 1139 行附近）。
   - Macro 数据源接入（当前 regime 恒为 UNKNOWN+缺口）。
   - PB 分位（中证指数接口当前仅 PE/股息率）。
3. 每次 session 结束必须更新本文件。

## 风险 / 纪律（不变）

- 阈值全部走版本化 Config（market-intel-v1 / market-regime-v1 /
  risk-review-v1 / research-quality-v1 / fear-memory-v1），禁止裸改常量。
- 估计必须显式标注（ESTIMATED）；缺口禁止静默填充。
- PIT 纪律：历史研究输入只可见 date <= as_of 的数据；fear_memory 案例
  start_date <= as_of 才可见；research_quality 是事后复盘，不得进入 PIT
  研究报告。
- 本地 commit 为 checkpoint，格式 feat:/fix:/refactor:/docs:，无 DCO。

## 关键文件

- `agent/src/investment_research/models/`：market_intelligence.py、
  market_regime.py、risk_review.py、fear_memory.py、research_quality.py、
  research_context.py（接线中枢）、artifact.py
- `agent/src/value_hunter/providers.py`（P1.5/P3 provider 增强）
- `agent/tests/`：对应 6 个新测试文件 + 契约/路由/缓存套件
- `automation/long_runner.py` + `tasks/roadmap.yaml`（队列，全部 done）
- `docs/status/`：phase0_8 / phase1 / phase2 / phase5 / phase6 文档 + 本文件
